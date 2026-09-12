"""Port: the transaction boundary.

The invariant this exists to protect:

    async with uow:
        await uow.leads.add(lead)               # the lead
        await uow.activities.add(activity)      # the audit trail entry
        await uow.outbox.add(event)             # the intent to call HubSpot
        await uow.commit()                      # all three, or none

Those three writes must share one PostgreSQL transaction. If the lead were
committed first and the outbox row second, a process crash in between would
leave a lead that HubSpot never hears about — silently, and forever. There is no
ordering of "commit locally" and "call a remote API" that is safe, because you
cannot commit two systems atomically. Writing the *intent* into the same
transaction as the data is the way out, and it works because it is all one
database.

The three repositories are attributes rather than separate injected
dependencies precisely so that sharing a session is structural rather than a
convention someone breaks at 11pm.

Implemented by app.infrastructure.database.unit_of_work.SqlAlchemyUnitOfWork.
Faked by tests.fakes.FakeUnitOfWork.
"""

from types import TracebackType
from typing import Protocol, Self

from app.application.ports.repositories import (
    ActivityRepository,
    LeadRepository,
    OutboxRepository,
)


class UnitOfWork(Protocol):
    """An atomic unit of work over the application's persistent state.

    Implementations own exactly one database session and hand it to every
    repository they expose. Leaving the context manager without calling
    `commit()` rolls back — the safe default, so a use case that raises halfway
    through cannot leave a partial write behind.
    """

    leads: LeadRepository
    activities: ActivityRepository
    outbox: OutboxRepository

    async def __aenter__(self) -> Self:
        """Begin the unit of work."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """End it, rolling back unless commit() was called."""
        ...

    async def commit(self) -> None:
        """Make every write in this unit of work durable, atomically."""
        ...

    async def rollback(self) -> None:
        """Discard every write in this unit of work."""
        ...
