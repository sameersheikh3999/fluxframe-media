"""Synchronising a captured lead into the CRM.

This is the consumer of the `LeadCaptured` outbox event. It runs *after* the
visitor has already received their 201, which is the entire point: HubSpot being
slow, down, misconfigured or absent can never cost Fluxframe a lead.

Idempotency matters here more than anywhere else in the system. The outbox
guarantees at-least-once delivery, so this method WILL be called twice for the
same lead eventually — a retry after a timeout that actually succeeded, a
reclaimed stalled row, a replayed dead letter. Two defences:

  1. If the lead already has a `crm_contact_id`, there is nothing to do.
  2. The CrmClient adapter upserts on email rather than blind-creating, so even
     a genuine second call updates rather than duplicates.

At-least-once delivery + an idempotent consumer = effectively-once, without any
of the machinery that exactly-once delivery would require.
"""

from uuid import UUID

from app.application.errors import (
    CrmPermanentError,
    CrmTransientError,
)
from app.application.ports.clock import Clock
from app.application.ports.crm_client import CrmClient, CrmContactUpsert
from app.application.ports.unit_of_work import UnitOfWork
from app.domain.leads.activities import ActivityType, LeadActivity
from app.domain.leads.entities import Lead


class CrmSyncService:
    """Pushes a lead into the CRM and records the outcome on the lead."""

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        crm_client: CrmClient,
        clock: Clock,
        sync_demo_leads: bool,
    ) -> None:
        self._uow = uow
        self._crm = crm_client
        self._clock = clock
        self._sync_demo_leads = sync_demo_leads

    async def sync_lead(self, lead_id: UUID) -> None:
        """Upsert one lead into the CRM.

        Raises CrmTransientError to ask the dispatcher for a retry, or
        CrmPermanentError to tell it not to bother. Anything else means success.
        """
        now = self._clock.now()

        async with self._uow:
            lead = await self._uow.leads.get(lead_id)
            if lead is None:
                # The lead was deleted between the event being written and
                # delivered. Nothing to sync; not an error.
                return

            skip_reason = self._should_skip(lead)
            if skip_reason is not None:
                lead.mark_crm_skipped(skip_reason, now)
                await self._uow.leads.update(lead)
                await self._uow.activities.add(
                    LeadActivity(
                        lead_id=lead.id,
                        activity_type=ActivityType.CRM_SYNC_SKIPPED,
                        description=f"CRM sync skipped: {skip_reason}",
                        occurred_at=now,
                    )
                )
                await self._uow.commit()
                return

            if lead.crm_contact_id:
                # Already synced. A replayed or duplicated event lands here.
                return

            contact = _to_crm_contact(lead)

        # The network call happens OUTSIDE the transaction, on purpose. Holding
        # a database transaction open across a multi-second HTTP request ties up
        # a connection from a small pool and turns a slow CRM into a database
        # incident.
        try:
            ref = await self._crm.upsert_contact(contact)
        except (CrmTransientError, CrmPermanentError) as exc:
            await self._record_failure(lead_id, str(exc))
            raise

        await self._record_success(lead_id, ref.contact_id)

    def _should_skip(self, lead: Lead) -> str | None:
        if not self._crm.is_configured:
            return "No CRM credential is configured."
        if lead.is_demo and not self._sync_demo_leads:
            # Default-off. Ten synthetic contacts per click would pollute a real
            # HubSpot portal you may want to show a client.
            return "Demo leads are not synced to the CRM."
        return None

    async def _record_success(self, lead_id: UUID, contact_id: str) -> None:
        now = self._clock.now()
        async with self._uow:
            lead = await self._uow.leads.get(lead_id)
            if lead is None:
                return
            lead.mark_crm_synced(contact_id, now)
            await self._uow.leads.update(lead)
            await self._uow.activities.add(
                LeadActivity(
                    lead_id=lead.id,
                    activity_type=ActivityType.CRM_SYNCED,
                    description=f"Synced to CRM as contact {contact_id}.",
                    occurred_at=now,
                    activity_metadata={"crm_contact_id": contact_id},
                )
            )
            await self._uow.commit()

    async def _record_failure(self, lead_id: UUID, error: str) -> None:
        now = self._clock.now()
        async with self._uow:
            lead = await self._uow.leads.get(lead_id)
            if lead is None:
                return
            lead.mark_crm_failed(error, now)
            await self._uow.leads.update(lead)
            await self._uow.activities.add(
                LeadActivity(
                    lead_id=lead.id,
                    activity_type=ActivityType.CRM_SYNC_FAILED,
                    description=f"CRM sync failed: {error}",
                    occurred_at=now,
                    activity_metadata={"error": error[:500]},
                )
            )
            await self._uow.commit()


def _to_crm_contact(lead: Lead) -> CrmContactUpsert:
    """Translate a domain Lead into the CRM port's vocabulary.

    Still Fluxframe's language — the HubSpot property names appear one layer
    further out, in app/infrastructure/hubspot/mapper.py.
    """
    return CrmContactUpsert(
        email=lead.contact.email,
        first_name=lead.contact.first_name,
        last_name=lead.contact.last_name,
        company_name=lead.contact.company_name,
        phone=lead.contact.phone,
        website=lead.contact.website,
        industry=lead.answers.industry.value,
        monthly_revenue=lead.answers.monthly_revenue.value,
        marketing_budget=lead.answers.monthly_marketing_budget.value,
        content_volume=lead.answers.content_volume.value,
        primary_goal=lead.answers.primary_goal.value,
        start_timeline=lead.answers.start_timeline.value,
        lead_score=lead.score or 0,
        lead_temperature=(lead.temperature.value if lead.temperature else "unknown"),
        lead_source=lead.source.value,
        is_demo=lead.is_demo,
    )
