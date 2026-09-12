"""Handlers that consume outbox events.

A handler is the bridge between the generic dispatcher (which knows about
claiming rows and scheduling retries) and a specific use case (which knows what
a LeadCaptured event means). It contains no business logic of its own — it
unpacks the event and calls a service.

Registering a new consumer is adding one entry to `build_handlers`. That is what
"the service must not depend on who cares about its events" buys: adding a Slack
notification later means writing a handler and one dictionary line, with no
change to LeadService.
"""

from uuid import UUID

from app.application.ports.outbox_store import OutboxRecord
from app.application.services.crm_sync_service import CrmSyncService
from app.application.services.outbox_dispatcher import EventHandler
from app.domain.leads.events import LeadCaptured
from app.observability.logging import get_logger

_logger = get_logger(__name__)


class CrmSyncHandler:
    """Consumes LeadCaptured by pushing the lead into the CRM."""

    def __init__(self, service: CrmSyncService) -> None:
        self._service = service

    async def handle(self, record: OutboxRecord) -> None:
        lead_id = _lead_id(record)
        if lead_id is None:
            # A malformed payload cannot be fixed by retrying. Returning
            # normally marks it processed rather than looping forever.
            _logger.warning("outbox_event_missing_lead_id", event_id=str(record.id))
            return
        await self._service.sync_lead(lead_id)


def build_handlers(crm_sync: CrmSyncService) -> dict[str, EventHandler]:
    """The event_type -> handler routing table.

    Events with no entry here are marked processed and skipped by the
    dispatcher. LeadMarkedHot and LeadStatusChanged are written to the outbox
    today and consumed by nobody — that is deliberate: the events are the
    historical record, and a consumer can be added later without a migration.
    """
    return {LeadCaptured.event_type: CrmSyncHandler(crm_sync)}


def _lead_id(record: OutboxRecord) -> UUID | None:
    raw = record.payload.get("lead_id")
    if isinstance(raw, str):
        try:
            return UUID(raw)
        except ValueError:
            return None
    return record.aggregate_id
