"""Port: operating the outbox queue.

Separate from `OutboxRepository` (which only appends, inside someone else's
transaction) because the dispatcher's needs are different: it claims work,
reports outcomes and schedules retries, each in its own short transaction.

The claim step is the interesting one. The PostgreSQL implementation uses
`FOR UPDATE SKIP LOCKED`, which lets two Railway replicas poll the same table
concurrently without ever handing the same row to both. That is a built-in
work-queue primitive, and it is the reason this system needs no Redis, no Celery
and no external broker to be correct under horizontal scaling.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class OutboxRecord:
    """One event awaiting (or having completed) delivery."""

    id: UUID
    event_type: str
    event_version: int
    aggregate_type: str
    aggregate_id: UUID
    payload: dict[str, object]
    correlation_id: str | None
    attempts: int
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class DispatchReport:
    """What one dispatcher pass did. Returned so the API and logs can show it."""

    claimed: int
    processed: int
    failed: int
    dead_lettered: int
    skipped: int


class OutboxStore(Protocol):
    """Claim and resolve outbox work."""

    async def claim_batch(self, limit: int, now: datetime) -> list[OutboxRecord]:
        """Atomically take up to `limit` due events and mark them in-flight.

        Must be safe to call concurrently from multiple processes.
        """
        ...

    async def mark_processed(self, event_id: UUID, now: datetime) -> None:
        """Delivery succeeded. Terminal."""
        ...

    async def mark_failed(
        self,
        event_id: UUID,
        error: str,
        next_attempt_at: datetime,
        now: datetime,
    ) -> None:
        """Delivery failed but may succeed later. Schedules the retry."""
        ...

    async def mark_dead(self, event_id: UUID, error: str, now: datetime) -> None:
        """Give up: either permanently failed, or out of attempts.

        A dead letter here is a status and a dashboard filter, not a separate
        queue. Keeping it in the same table means replaying one is an UPDATE.
        """
        ...

    async def reclaim_stalled(self, older_than: datetime, now: datetime) -> int:
        """Return rows stuck in-flight to the pending pool.

        A worker that dies mid-delivery leaves its claimed rows marked
        `processing` forever. This is the janitor that frees them. It is safe
        precisely because consumers are idempotent: reprocessing is harmless.
        """
        ...

    async def replay(self, event_id: UUID, now: datetime) -> bool:
        """Put a dead-lettered event back in the queue. Returns False if absent."""
        ...
