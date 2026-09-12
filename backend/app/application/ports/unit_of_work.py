"""Port: the transaction boundary.

NOT IMPLEMENTED IN PHASE 0. This file declares the contract only; the first
adapter (``SqlAlchemyUnitOfWork``) and the first repositories arrive in Phase 1.
It is here because the boundary it describes is an approved architectural
decision (docs/decisions/0004-unit-of-work-owns-the-transaction.md), and writing
it down now is what stops Phase 1 from quietly reaching for a raw AsyncSession.

The invariant it exists to protect, from Phase 3 onward:

    async with uow:
        await uow.leads.add(lead)               # the lead
        await uow.activities.add(activity)      # the audit trail entry
        await uow.outbox.add(event)             # the intent to call HubSpot
        await uow.commit()                      # all three, or none

Those three writes must share one PostgreSQL transaction. If the lead were
committed first and the outbox row second, a process crash in between would
leave a lead that HubSpot never hears about — silently, and forever.

Repository attributes (``uow.leads``, ``uow.outbox``, ...) are added to this
Protocol in the phase that introduces them. They are not declared up front,
because a port should describe what the application actually needs today.
"""

from types import TracebackType
from typing import Protocol, Self


class UnitOfWork(Protocol):
    """An atomic unit of work over the application's persistent state.

    Implementations own exactly one database session. Leaving the context
    manager without calling ``commit()`` rolls back — the safe default, so that
    a use case which raises halfway through cannot leave a partial write behind.
    """

    async def __aenter__(self) -> Self:
        """Begin the unit of work."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """End the unit of work, rolling back unless ``commit()`` was called."""
        ...

    async def commit(self) -> None:
        """Make every write in this unit of work durable, atomically."""
        ...

    async def rollback(self) -> None:
        """Discard every write in this unit of work."""
        ...
