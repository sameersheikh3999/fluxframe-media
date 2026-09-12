"""Write-side ports: how the application persists domain objects.

These deal in domain entities, never in rows. A repository's job is to make
persistence look like an in-memory collection to the layer above it, so that
`LeadService` reads as business logic rather than as data access.

All three are obtained from a `UnitOfWork`, never constructed directly. That is
what guarantees they share one transaction — see ports/unit_of_work.py.
"""

from typing import Protocol
from uuid import UUID

from app.domain.leads.activities import LeadActivity
from app.domain.leads.entities import Lead
from app.domain.shared.events import DomainEvent


class LeadRepository(Protocol):
    """Stores and retrieves Lead aggregates."""

    async def add(self, lead: Lead) -> None:
        """Stage a new lead for insertion. Not durable until commit()."""
        ...

    async def update(self, lead: Lead) -> None:
        """Stage changes to an existing lead."""
        ...

    async def get(self, lead_id: UUID) -> Lead | None:
        """Load one lead by id, or None."""
        ...

    async def find_by_idempotency_key(self, key: str) -> Lead | None:
        """The duplicate-submission check.

        A unique index on the column is what makes this safe under concurrency;
        this lookup is the fast path that avoids relying on the exception.
        """
        ...

    async def count_recent_by_email(self, email: str, since_hours: int) -> int:
        """How many leads this address submitted recently.

        Used as a *signal*, never as a constraint. Someone genuinely enquiring
        again months later is a new lead, so email is not unique — but three
        submissions in an hour is worth surfacing on the dashboard.
        """
        ...


class ActivityRepository(Protocol):
    """Appends to a lead's audit trail. Append-only by design: history is not
    edited, so there is no `update` here."""

    async def add(self, activity: LeadActivity) -> None: ...

    async def list_for_lead(self, lead_id: UUID) -> list[LeadActivity]: ...


class OutboxRepository(Protocol):
    """Stores domain events for later delivery.

    The whole point of this port is that `add` participates in the caller's
    transaction. If it committed on its own, the outbox pattern would be
    pointless — the event could be written while the lead was rolled back.
    """

    async def add(self, event: DomainEvent, correlation_id: str | None = None) -> None:
        """Stage one event. Durable only when the unit of work commits."""
        ...
