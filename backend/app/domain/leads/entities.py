"""The Lead aggregate — the centre of the domain.

This is a plain dataclass with methods, not a Pydantic model and not a
SQLAlchemy model. It holds state *and* enforces the rules about that state, and
it can be constructed, scored and transitioned in a unit test with nothing
installed but Python.

The single most important property: a Lead cannot be put into an invalid state
through any code path. `transition_to` consults the lifecycle table, so the API,
the dashboard, a background worker and a future AI agent all get the same
answer. There is no "just this once" route around it.

Events are *collected*, not dispatched. The entity appends to `_pending_events`;
the application service drains them and writes them to the outbox inside the
same transaction as the lead. The domain therefore never performs I/O, and the
atomicity guarantee lives where it belongs.
"""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.domain.leads.enums import (
    ContentVolume,
    CrmSyncStatus,
    Industry,
    LeadSource,
    LeadStatus,
    LeadTemperature,
    MarketingBudget,
    MonthlyRevenue,
    PrimaryGoal,
    StartTimeline,
)
from app.domain.leads.errors import IllegalLeadTransitionError, InvalidLeadDataError
from app.domain.leads.events import LeadCaptured, LeadMarkedHot, LeadStatusChanged
from app.domain.leads.lifecycle import can_transition
from app.domain.leads.scoring import ScoreResult, ScoringInput, score_lead
from app.domain.shared.events import DomainEvent

MAX_MESSAGE_LENGTH = 5000


@dataclass(frozen=True, slots=True)
class Attribution:
    """Where this lead came from, for marketing analysis.

    A value object: it has no identity of its own and is always replaced
    wholesale rather than edited. Grouping the eight UTM-ish fields here keeps
    the Lead signature readable and means attribution logic has somewhere
    obvious to live later.

    Note what is NOT here: the visitor's IP address. It adds a GDPR obligation
    and answers nothing that the UTM parameters do not already answer.
    """

    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    utm_content: str | None = None
    utm_term: str | None = None
    referrer: str | None = None
    landing_page: str | None = None


@dataclass(frozen=True, slots=True)
class ContactDetails:
    """Who the lead is."""

    first_name: str
    last_name: str
    email: str
    company_name: str
    website: str | None = None
    phone: str | None = None

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


@dataclass(frozen=True, slots=True)
class QualificationAnswers:
    """What the lead told us about their business and their intent."""

    industry: Industry
    monthly_revenue: MonthlyRevenue
    monthly_marketing_budget: MarketingBudget
    content_volume: ContentVolume
    primary_goal: PrimaryGoal
    start_timeline: StartTimeline
    message: str | None = None

    def to_scoring_input(self) -> ScoringInput:
        """Narrow these answers to exactly what the scoring function needs."""
        return ScoringInput(
            monthly_marketing_budget=self.monthly_marketing_budget,
            content_volume=self.content_volume,
            start_timeline=self.start_timeline,
            primary_goal=self.primary_goal,
            industry=self.industry,
        )


@dataclass(slots=True)
class Lead:
    """A prospective client who asked for a strategy call.

    Mutable, unlike the value objects above, because a lead genuinely changes
    over its life: it gets scored, contacted, won or lost.
    """

    id: UUID
    idempotency_key: str
    contact: ContactDetails
    answers: QualificationAnswers
    attribution: Attribution
    source: LeadSource
    is_demo: bool
    created_at: datetime
    updated_at: datetime

    status: LeadStatus = LeadStatus.NEW
    score: int | None = None
    temperature: LeadTemperature | None = None
    score_version: str | None = None
    score_breakdown: dict[str, object] | None = None

    crm_sync_status: CrmSyncStatus = CrmSyncStatus.PENDING
    crm_contact_id: str | None = None
    crm_synced_at: datetime | None = None
    crm_sync_error: str | None = None
    crm_sync_attempts: int = 0

    _pending_events: list[DomainEvent] = field(default_factory=list, repr=False)

    # --- construction --------------------------------------------------------

    @classmethod
    def capture(
        cls,
        *,
        idempotency_key: str,
        contact: ContactDetails,
        answers: QualificationAnswers,
        attribution: Attribution,
        source: LeadSource,
        now: datetime,
        is_demo: bool = False,
        lead_id: UUID | None = None,
    ) -> "Lead":
        """Create a lead, score it, and record what happened.

        A factory rather than a bare constructor because capturing a lead is a
        business operation with rules attached, not just field assignment. The
        id is generated here rather than by the database so that the outbox
        event written in the same transaction can reference it.

        `now` is passed in rather than read from the clock: the domain does not
        perform I/O, and reading the system clock is I/O.
        """
        cls._validate(idempotency_key, contact, answers)

        lead = cls(
            id=lead_id or uuid4(),
            idempotency_key=idempotency_key,
            contact=contact,
            answers=answers,
            attribution=attribution,
            source=source,
            is_demo=is_demo,
            created_at=now,
            updated_at=now,
        )

        result = score_lead(answers.to_scoring_input())
        lead._apply_score(result)

        lead._pending_events.append(
            LeadCaptured(
                aggregate_id=lead.id,
                occurred_at=now,
                payload={
                    "lead_id": str(lead.id),
                    "email": contact.email,
                    "company_name": contact.company_name,
                    "source": source.value,
                    "is_demo": is_demo,
                    "score": result.score,
                    "temperature": result.temperature.value,
                },
            )
        )

        if result.temperature is LeadTemperature.HOT:
            lead._pending_events.append(
                LeadMarkedHot(
                    aggregate_id=lead.id,
                    occurred_at=now,
                    payload={
                        "lead_id": str(lead.id),
                        "company_name": contact.company_name,
                        "score": result.score,
                    },
                )
            )

        return lead

    @staticmethod
    def _validate(
        idempotency_key: str,
        contact: ContactDetails,
        answers: QualificationAnswers,
    ) -> None:
        """Business-level validation.

        Distinct from the transport validation Pydantic performs at the edge.
        Pydantic checks "is this a well-formed email string". This checks the
        things the business cares about, and it runs no matter who called us.
        """
        if not idempotency_key.strip():
            raise InvalidLeadDataError("An idempotency key is required.")
        if not contact.first_name.strip() or not contact.last_name.strip():
            raise InvalidLeadDataError("A first and last name are required.")
        if "@" not in contact.email:
            raise InvalidLeadDataError("A valid email address is required.")
        if not contact.company_name.strip():
            raise InvalidLeadDataError("A company name is required.")
        if answers.message and len(answers.message) > MAX_MESSAGE_LENGTH:
            raise InvalidLeadDataError(f"Message must be {MAX_MESSAGE_LENGTH} characters or fewer.")

    # --- behaviour -----------------------------------------------------------

    def _apply_score(self, result: ScoreResult) -> None:
        self.score = result.score
        self.temperature = result.temperature
        self.score_version = result.version
        self.score_breakdown = result.to_breakdown()

    def rescore(self, now: datetime) -> ScoreResult:
        """Recompute the score under the current rules.

        Explicit, never automatic. Re-scoring silently would rewrite the
        explanation attached to a lead a salesperson has already acted on.
        """
        result = score_lead(self.answers.to_scoring_input())
        self._apply_score(result)
        self.updated_at = now
        return result

    def transition_to(self, new_status: LeadStatus, now: datetime) -> None:
        """Move the lead through the sales lifecycle.

        The guard is the reason this method exists. Every caller in the system
        goes through it, so an illegal transition is impossible rather than
        merely discouraged.
        """
        if new_status is self.status:
            return
        if not can_transition(self.status, new_status):
            raise IllegalLeadTransitionError(self.status, new_status)

        previous = self.status
        self.status = new_status
        self.updated_at = now
        self._pending_events.append(
            LeadStatusChanged(
                aggregate_id=self.id,
                occurred_at=now,
                payload={
                    "lead_id": str(self.id),
                    "from_status": previous.value,
                    "to_status": new_status.value,
                },
            )
        )

    # --- CRM synchronisation state ------------------------------------------
    #
    # These record the OUTCOME of a sync that infrastructure performed. The
    # domain still never calls HubSpot; it only knows that syncing is a thing
    # that can succeed, fail or be skipped.

    def mark_crm_synced(self, contact_id: str, now: datetime) -> None:
        self.crm_sync_status = CrmSyncStatus.SYNCED
        self.crm_contact_id = contact_id
        self.crm_synced_at = now
        self.crm_sync_error = None
        self.updated_at = now

    def mark_crm_failed(self, error: str, now: datetime) -> None:
        self.crm_sync_status = CrmSyncStatus.FAILED
        self.crm_sync_error = error[:1000]
        self.crm_sync_attempts += 1
        self.updated_at = now

    def mark_crm_skipped(self, reason: str, now: datetime) -> None:
        self.crm_sync_status = CrmSyncStatus.SKIPPED
        self.crm_sync_error = reason[:1000]
        self.updated_at = now

    # --- events --------------------------------------------------------------

    def collect_events(self) -> list[DomainEvent]:
        """Hand over the pending events and forget them.

        Called by the application service, which writes them to the outbox in
        the same transaction as the lead. Draining here means an event cannot
        be written twice by an accidental second call.
        """
        events = list(self._pending_events)
        self._pending_events.clear()
        return events
