"""The SQLAlchemy Unit of Work — where the outbox invariant is actually kept.

One `AsyncSession` per `async with` block, shared by all three repositories.
That sharing is the whole mechanism: when `commit()` runs, the lead, its
activity rows and its outbox events go to the database in a single transaction,
so the "lead saved but HubSpot never told" failure mode cannot happen.

Two implementation details that are easy to get wrong:

**Re-entrancy.** A fresh session is created on every `__aenter__`, so one
injected UnitOfWork can be entered repeatedly. The demo generator relies on
this: ten leads, ten independent transactions, lead seven failing without
rolling back leads one to six.

**Rollback by default.** Leaving the block without calling `commit()` rolls
back. A use case that raises halfway through cannot leave a partial write.

Async SQLAlchemy note: `AsyncSession` is NOT safe to share across concurrent
tasks. Each request gets its own, which the composition root guarantees by
building a new UnitOfWork per request.
"""

from types import TracebackType
from typing import Self

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.errors import IdempotencyConflictError
from app.application.ports.repositories import (
    ActivityRepository,
    LeadRepository,
    OutboxRepository,
)
from app.infrastructure.database.repositories import (
    SqlAlchemyActivityRepository,
    SqlAlchemyLeadRepository,
    SqlAlchemyOutboxRepository,
)
from app.observability.logging import get_logger

_logger = get_logger(__name__)


class SqlAlchemyUnitOfWork:
    """An atomic unit of work backed by one AsyncSession.

    Satisfies app.application.ports.unit_of_work.UnitOfWork structurally — it
    neither imports nor inherits from the Protocol.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._committed = False

        # Declared as the PORT types, not the concrete classes. A Protocol's
        # mutable attributes are invariant, so annotating these as
        # SqlAlchemyLeadRepository would stop this class from satisfying
        # UnitOfWork. mypy catches that at the composition root, which is
        # exactly where conformance is supposed to be checked.
        self.leads: LeadRepository
        self.activities: ActivityRepository
        self.outbox: OutboxRepository

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        self._committed = False
        self.leads = SqlAlchemyLeadRepository(self._session)
        self.activities = SqlAlchemyActivityRepository(self._session)
        self.outbox = SqlAlchemyOutboxRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        session = self._session
        if session is None:
            return
        try:
            if not self._committed:
                # Rollback is the default. Reaching here without a commit means
                # either an exception, or a use case that decided not to write.
                await session.rollback()
        finally:
            await session.close()
            self._session = None

    async def commit(self) -> None:
        """Flush and commit every staged write, atomically."""
        if self._session is None:
            raise RuntimeError("commit() called outside an active unit of work.")
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            # The only unique constraint a caller can realistically trip is the
            # idempotency key: two concurrent submissions of the same form,
            # where both passed the pre-check before either committed. The
            # database is the arbiter, and this translates its answer into a
            # domain-meaningful error rather than a 500.
            if _is_idempotency_violation(exc):
                raise IdempotencyConflictError("This submission was already received.") from exc
            raise
        self._committed = True

    async def rollback(self) -> None:
        if self._session is not None:
            await self._session.rollback()


def _is_idempotency_violation(exc: IntegrityError) -> bool:
    """Was this a duplicate idempotency key rather than some other constraint?

    Matching on the constraint name is why `NAMING_CONVENTION` in base.py
    matters: the name is deterministic and identical on every database.
    """
    message = str(exc.orig) if exc.orig else str(exc)
    return "idempotency_key" in message.lower()
