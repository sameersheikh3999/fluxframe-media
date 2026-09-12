"""The lead use cases — the application's most important service.

Read `capture_lead` as a transaction script. Every line is either a domain call
or a repository call, and the transaction boundary is visible on the page. There
is no SQL here, no HTTP, no HubSpot, no `datetime.now()`.

The two things worth understanding in this file:

1.  **Idempotency.** A visitor double-clicking Submit sends the same request
    twice. We check for the key first (fast path) and rely on the unique index
    to settle the race (correct path).

2.  **The outbox invariant.** The lead, its activity rows and the domain events
    are written inside ONE transaction. The HubSpot call happens later, driven
    by those events. If HubSpot is down, or the token is wrong, or the whole
    integration is switched off, the visitor still gets a 201.
"""

from collections.abc import Sequence
from uuid import UUID

from app.application.dto.leads import CaptureLeadCommand, LeadCaptureResult
from app.application.errors import LeadNotFoundError
from app.application.ports.clock import Clock
from app.application.ports.unit_of_work import UnitOfWork
from app.domain.leads.activities import LeadActivity
from app.domain.leads.entities import (
    Attribution,
    ContactDetails,
    Lead,
    QualificationAnswers,
)
from app.domain.leads.enums import LeadStatus
from app.domain.leads.lifecycle import next_statuses
from app.domain.shared.events import DomainEvent

#: Window used for the "this address has submitted before" dashboard signal.
DUPLICATE_EMAIL_WINDOW_HOURS = 24


class LeadService:
    """Capturing leads and moving them through the sales lifecycle."""

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._clock = clock

    async def capture_lead(
        self,
        command: CaptureLeadCommand,
        correlation_id: str | None = None,
    ) -> LeadCaptureResult:
        """Capture, score and store one lead. The system's primary use case."""
        now = self._clock.now()

        async with self._uow:
            # --- Idempotency, fast path -------------------------------------
            # A genuine retry (double-click, flaky network, client-side retry)
            # carries the key we already stored. Return the original result and
            # write nothing: no duplicate lead, no duplicate HubSpot contact.
            existing = await self._uow.leads.find_by_idempotency_key(command.idempotency_key)
            if existing is not None:
                return LeadCaptureResult(
                    id=existing.id,
                    created_at=existing.created_at,
                    was_duplicate=True,
                )

            # --- Domain constructs and scores itself ------------------------
            # Note what this service does NOT do: it does not compute a score.
            # Lead.capture() runs the deterministic rules and records the
            # events. Scoring logic lives in one place and one place only.
            lead = Lead.capture(
                idempotency_key=command.idempotency_key,
                contact=ContactDetails(
                    first_name=command.first_name,
                    last_name=command.last_name,
                    email=command.email,
                    company_name=command.company_name,
                    website=command.website,
                    phone=command.phone,
                ),
                answers=QualificationAnswers(
                    industry=command.industry,
                    monthly_revenue=command.monthly_revenue,
                    monthly_marketing_budget=command.monthly_marketing_budget,
                    content_volume=command.content_volume,
                    primary_goal=command.primary_goal,
                    start_timeline=command.start_timeline,
                    message=command.message,
                ),
                attribution=Attribution(
                    utm_source=command.attribution.utm_source,
                    utm_medium=command.attribution.utm_medium,
                    utm_campaign=command.attribution.utm_campaign,
                    utm_content=command.attribution.utm_content,
                    utm_term=command.attribution.utm_term,
                    referrer=command.attribution.referrer,
                    landing_page=command.attribution.landing_page,
                ),
                source=command.source,
                now=now,
                is_demo=command.is_demo,
            )

            # --- Everything below commits together ---------------------------
            await self._uow.leads.add(lead)

            actor = "demo_generator" if command.is_demo else "system"
            await self._uow.activities.add(
                LeadActivity.captured(lead.id, now, command.source.value, actor)
            )
            if lead.score is not None and lead.temperature is not None:
                await self._uow.activities.add(
                    LeadActivity.scored(
                        lead.id,
                        now,
                        lead.score,
                        lead.temperature.value,
                        lead.score_version or "unknown",
                    )
                )

            await self._publish(lead.collect_events(), correlation_id)

            # One commit. Lead + activities + outbox events, atomically.
            # A crash anywhere above this line leaves the database untouched.
            await self._uow.commit()

        return LeadCaptureResult(id=lead.id, created_at=lead.created_at, was_duplicate=False)

    async def transition_status(
        self,
        lead_id: UUID,
        new_status: LeadStatus,
        actor: str,
        correlation_id: str | None = None,
    ) -> LeadStatus:
        """Move a lead through the sales lifecycle.

        The legality check lives in the entity, not here, so the dashboard, a
        background worker and a future AI agent are all constrained identically.
        An illegal transition raises IllegalLeadTransitionError and nothing is
        written, because the commit never happens.
        """
        now = self._clock.now()

        async with self._uow:
            lead = await self._uow.leads.get(lead_id)
            if lead is None:
                raise LeadNotFoundError(f"No lead with id {lead_id}.")

            previous = lead.status
            lead.transition_to(new_status, now)  # raises if illegal

            await self._uow.leads.update(lead)
            await self._uow.activities.add(
                LeadActivity.status_changed(lead.id, now, previous.value, new_status.value, actor)
            )
            await self._publish(lead.collect_events(), correlation_id)
            await self._uow.commit()

        return lead.status

    async def rescore_lead(self, lead_id: UUID) -> int:
        """Recompute a lead's score under the current rules.

        Explicit and manual. Re-scoring automatically would rewrite the
        explanation attached to a lead a salesperson has already acted on.
        """
        now = self._clock.now()

        async with self._uow:
            lead = await self._uow.leads.get(lead_id)
            if lead is None:
                raise LeadNotFoundError(f"No lead with id {lead_id}.")

            result = lead.rescore(now)
            await self._uow.leads.update(lead)
            await self._uow.activities.add(
                LeadActivity.scored(
                    lead.id, now, result.score, result.temperature.value, result.version
                )
            )
            await self._uow.commit()

        return result.score

    @staticmethod
    def allowed_next_statuses(current: LeadStatus) -> tuple[str, ...]:
        """Which buttons the dashboard should render for this lead.

        The UI asks the domain rather than hardcoding a list, so the controls
        can never drift from the rules that would reject them.
        """
        return tuple(sorted(status.value for status in next_statuses(current)))

    async def _publish(self, events: Sequence[DomainEvent], correlation_id: str | None) -> None:
        """Stage domain events in the outbox, inside the caller's transaction.

        `correlation_id` is the HTTP request id, carried through so that a
        HubSpot call made ten seconds later can be traced back to the web
        request that caused it.
        """
        for event in events:
            await self._uow.outbox.add(event, correlation_id)
