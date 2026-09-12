"""Read-side use cases: everything the dashboard displays.

Separate from `LeadService` because reads and writes genuinely want different
things. A write loads one aggregate, applies a rule and saves it. A read wants
fifty flat rows with a COUNT, filtered and paginated. Forcing both through one
repository produces either half-built entities or a dashboard that rehydrates
fifty aggregates to render a table.

This service is thin on purpose — it delegates to a read model and adds the
small amount of policy that belongs to the application rather than to SQL
(clamping page size, deciding which next-statuses to offer). If it ever grows
business rules, those rules belong in the domain instead.
"""

from uuid import UUID

from app.application.dto.leads import (
    DashboardStats,
    LeadDetailView,
    LeadFilters,
    LeadPage,
)
from app.application.errors import LeadNotFoundError
from app.application.ports.read_models import LeadReadModel, OutboxReadModel

DEFAULT_PAGE_SIZE = 25
#: Hard cap. Without it, `?limit=100000` is a denial-of-service vector that
#: costs the caller one keystroke.
MAX_PAGE_SIZE = 100


class LeadQueryService:
    """Queries for the sales dashboard."""

    def __init__(
        self,
        *,
        leads: LeadReadModel,
        outbox: OutboxReadModel,
    ) -> None:
        self._leads = leads
        self._outbox = outbox

    async def list_leads(
        self,
        filters: LeadFilters,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> LeadPage:
        safe_limit = max(1, min(limit, MAX_PAGE_SIZE))
        safe_offset = max(0, offset)
        return await self._leads.list_leads(filters, safe_limit, safe_offset)

    async def get_lead(self, lead_id: UUID) -> LeadDetailView:
        detail = await self._leads.get_detail(lead_id)
        if detail is None:
            raise LeadNotFoundError(f"No lead with id {lead_id}.")
        return detail

    async def stats(self) -> DashboardStats:
        return await self._leads.stats()

    async def outbox_health(self) -> tuple[int, int]:
        """(pending, dead-lettered). Surfaced as a dashboard warning strip."""
        return (
            await self._outbox.pending_count(),
            await self._outbox.dead_letter_count(),
        )
