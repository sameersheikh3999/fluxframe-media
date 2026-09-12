"""The outbox queue, implemented on PostgreSQL.

The interesting method is `claim_batch`, and specifically this clause:

    .with_for_update(skip_locked=True)

`FOR UPDATE SKIP LOCKED` tells PostgreSQL: lock these rows, and if another
transaction already holds one, silently skip it rather than waiting. That single
clause is what makes this a correct work queue under horizontal scaling — two
Railway replicas can poll the same table at the same time and will never hand
the same event to both. It is the reason this system needs no Redis, no Celery
and no external broker to be reliable.

SQLite (tests only) ignores row locking, which is fine: the test suite is
single-process, so there is nothing to contend with.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ports.outbox_store import OutboxRecord
from app.infrastructure.database.models import OutboxEventModel

#: Statuses eligible to be picked up: never delivered, or failed and due again.
_CLAIMABLE = ("pending", "failed")


class SqlAlchemyOutboxStore:
    """Claims and resolves outbox work. Satisfies ports.OutboxStore."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def claim_batch(self, limit: int, now: datetime) -> list[OutboxRecord]:
        """Atomically take up to `limit` due events and mark them in flight."""
        async with self._session_factory() as session:
            stmt = (
                select(OutboxEventModel)
                .where(
                    OutboxEventModel.status.in_(_CLAIMABLE),
                    OutboxEventModel.next_attempt_at <= now,
                )
                .order_by(OutboxEventModel.occurred_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            rows = (await session.execute(stmt)).scalars().all()

            for row in rows:
                row.status = "processing"
                row.claimed_at = now
                # Incremented at claim time rather than on failure, so a worker
                # that dies mid-delivery still burns an attempt. Otherwise a
                # crash-looping consumer could retry forever without ever
                # reaching max_attempts.
                row.attempts += 1

            await session.commit()
            return [_to_record(row) for row in rows]

    async def mark_processed(self, event_id: UUID, now: datetime) -> None:
        await self._set(event_id, status="processed", processed_at=now, last_error=None)

    async def mark_failed(
        self,
        event_id: UUID,
        error: str,
        next_attempt_at: datetime,
        now: datetime,
    ) -> None:
        await self._set(
            event_id,
            status="failed",
            last_error=error[:2000],
            next_attempt_at=next_attempt_at,
            claimed_at=None,
        )

    async def mark_dead(self, event_id: UUID, error: str, now: datetime) -> None:
        await self._set(
            event_id,
            status="dead",
            last_error=error[:2000],
            processed_at=now,
            claimed_at=None,
        )

    async def reclaim_stalled(self, older_than: datetime, now: datetime) -> int:
        """Return rows abandoned by a dead worker to the pending pool.

        Safe because every consumer is idempotent: reprocessing an event that
        actually succeeded costs one no-op HubSpot upsert.
        """
        async with self._session_factory() as session:
            stmt = (
                update(OutboxEventModel)
                .where(
                    OutboxEventModel.status == "processing",
                    OutboxEventModel.claimed_at.is_not(None),
                    OutboxEventModel.claimed_at < older_than,
                )
                .values(status="pending", claimed_at=None, next_attempt_at=now)
            )
            result = await session.execute(stmt)
            await session.commit()
            # CursorResult carries rowcount; the generic Result type does not,
            # so read it defensively rather than asserting the subtype.
            return int(getattr(result, "rowcount", 0) or 0)

    async def replay(self, event_id: UUID, now: datetime) -> bool:
        """Put a dead-lettered event back in the queue, attempts reset."""
        async with self._session_factory() as session:
            row = await session.get(OutboxEventModel, event_id)
            if row is None:
                return False
            row.status = "pending"
            row.attempts = 0
            row.next_attempt_at = now
            row.claimed_at = None
            row.processed_at = None
            await session.commit()
            return True

    async def _set(self, event_id: UUID, **values: object) -> None:
        async with self._session_factory() as session:
            row = await session.get(OutboxEventModel, event_id)
            if row is None:
                return
            for key, value in values.items():
                setattr(row, key, value)
            await session.commit()


def _to_record(row: OutboxEventModel) -> OutboxRecord:
    return OutboxRecord(
        id=row.id,
        event_type=row.event_type,
        event_version=row.event_version,
        aggregate_type=row.aggregate_type,
        aggregate_id=row.aggregate_id,
        payload=dict(row.payload or {}),
        correlation_id=row.correlation_id,
        attempts=row.attempts,
        occurred_at=row.occurred_at,
    )
