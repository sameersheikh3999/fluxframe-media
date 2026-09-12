"""Read-side ports: how the dashboard queries data.

Kept separate from the write-side repositories on purpose, and it is worth
understanding why rather than treating it as ceremony.

Writes and reads want different shapes. A write loads one full `Lead` aggregate,
applies a rule, and saves it. A read wants fifty flat rows, filtered, sorted,
paginated, with a COUNT alongside them. Forcing both through one `LeadRepository`
means either the repository grows query methods that return half-built entities,
or the dashboard rehydrates fifty aggregates to render a table.

So: `LeadRepository` returns domain entities and is used inside transactions;
`LeadReadModel` returns view DTOs and is used for display. That is the useful 5%
of CQRS with none of the infrastructure — no separate database, no projections,
no eventual consistency. Just two interfaces over the same tables.

These are not on the UnitOfWork: reads do not need a transaction boundary.
"""

from typing import Protocol
from uuid import UUID

from app.application.dto.leads import (
    DashboardStats,
    LeadDetailView,
    LeadFilters,
    LeadPage,
)


class LeadReadModel(Protocol):
    """Queries that exist to be displayed."""

    async def list_leads(self, filters: LeadFilters, limit: int, offset: int) -> LeadPage:
        """A filtered, sorted, paginated page of dashboard rows."""
        ...

    async def get_detail(self, lead_id: UUID) -> LeadDetailView | None:
        """Everything the detail page shows, including the activity timeline."""
        ...

    async def stats(self) -> DashboardStats:
        """The counters across the top of the dashboard."""
        ...


class OutboxReadModel(Protocol):
    """Operational visibility into the event queue."""

    async def pending_count(self) -> int: ...

    async def dead_letter_count(self) -> int: ...
