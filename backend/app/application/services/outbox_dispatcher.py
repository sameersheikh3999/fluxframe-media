"""The outbox dispatcher — the reliability core of the system.

It runs one loop:

    claim a batch  ->  route each event to its handler  ->  record the outcome

and the outcome rules are where the engineering lives:

    success            mark processed. Terminal.
    transient failure  schedule a retry with exponential backoff + jitter
    permanent failure  dead-letter immediately; retrying a 401 forever only
                       hides a configuration bug behind a growing queue
    out of attempts    dead-letter

Why jitter: without it, a thousand events that failed during the same outage all
retry at the same instant and re-create the outage. Jitter spreads them out.

Why this is not Celery: the queue is a PostgreSQL table, which means enqueueing
an event is atomic with the business write that caused it. No external broker
can offer that, because a broker is a second system that cannot join your
transaction. Redis and Celery start earning their operational cost when you need
sub-second fan-out, scheduled jobs, or throughput this cannot reach — measure
first, and write the ADR when the day comes.
"""

import random
from datetime import timedelta
from typing import Protocol
from uuid import UUID

from app.application.errors import CrmPermanentError, CrmTransientError
from app.application.ports.clock import Clock
from app.application.ports.outbox_store import (
    DispatchReport,
    OutboxRecord,
    OutboxStore,
)

#: Cap on the backoff, so a long-dead integration still retries hourly rather
#: than drifting into never.
MAX_BACKOFF_SECONDS = 3600
BASE_BACKOFF_SECONDS = 2


class EventHandler(Protocol):
    """Consumes one kind of domain event."""

    async def handle(self, record: OutboxRecord) -> None:
        """Process the event.

        Raise CrmPermanentError to dead-letter immediately. Raise anything else
        to request a retry.
        """
        ...


def compute_backoff(attempts: int, rng: random.Random) -> timedelta:
    """Exponential backoff with full jitter: ~2s, ~4s, ~8s ... capped at an hour.

    `attempts` includes the attempt that just failed, so the first retry waits
    around two seconds rather than one.
    """
    ceiling = min(BASE_BACKOFF_SECONDS ** max(attempts, 1), MAX_BACKOFF_SECONDS)
    return timedelta(seconds=rng.uniform(ceiling / 2, ceiling))


def retry_delay(exc: BaseException, attempts: int, rng: random.Random) -> timedelta:
    """How long to wait before trying this event again.

    A provider that sent `Retry-After` gets to decide. Retrying sooner than a
    rate limiter asked is how a short throttle becomes a long one.
    """
    if isinstance(exc, CrmTransientError) and exc.retry_after_seconds:
        return timedelta(seconds=exc.retry_after_seconds)
    return compute_backoff(attempts, rng)


class OutboxDispatcher:
    """Drains the outbox, one batch at a time."""

    def __init__(
        self,
        *,
        store: OutboxStore,
        handlers: dict[str, EventHandler],
        clock: Clock,
        batch_size: int = 20,
        max_attempts: int = 6,
        stalled_after_seconds: int = 300,
        rng: random.Random | None = None,
    ) -> None:
        self._store = store
        self._handlers = handlers
        self._clock = clock
        self._batch_size = batch_size
        self._max_attempts = max_attempts
        self._stalled_after_seconds = stalled_after_seconds
        self._rng = rng or random.Random()

    async def dispatch_once(self) -> DispatchReport:
        """Run one pass. Safe to call concurrently from several processes."""
        now = self._clock.now()

        # Free rows abandoned by a worker that died mid-delivery. Safe because
        # every handler is idempotent, so reprocessing costs nothing.
        await self._store.reclaim_stalled(
            older_than=now - timedelta(seconds=self._stalled_after_seconds),
            now=now,
        )

        records = await self._store.claim_batch(self._batch_size, now)
        processed = failed = dead = skipped = 0

        for record in records:
            handler = self._handlers.get(record.event_type)
            if handler is None:
                # An event nobody consumes is not a failure. LeadMarkedHot has
                # no handler until someone writes a notifier, and marking it
                # processed keeps the queue from filling with permanent noise.
                await self._store.mark_processed(record.id, self._clock.now())
                skipped += 1
                continue

            outcome = await self._deliver(record)
            if outcome == "processed":
                processed += 1
            elif outcome == "failed":
                failed += 1
            else:
                dead += 1

        return DispatchReport(
            claimed=len(records),
            processed=processed,
            failed=failed,
            dead_lettered=dead,
            skipped=skipped,
        )

    async def _deliver(self, record: OutboxRecord) -> str:
        """Attempt one event and resolve it. Returns the outcome as a string."""
        handler = self._handlers[record.event_type]
        try:
            await handler.handle(record)
        except CrmPermanentError as exc:
            await self._store.mark_dead(record.id, str(exc), self._clock.now())
            return "dead"
        except Exception as exc:
            # Unknown exceptions are treated as transient. Optimism is the safer
            # default here: a genuine bug surfaces as a dead letter after
            # max_attempts, whereas treating everything unknown as permanent
            # would silently drop recoverable work on the first blip.
            if record.attempts >= self._max_attempts:
                await self._store.mark_dead(
                    record.id,
                    f"Giving up after {record.attempts} attempts: {exc}",
                    self._clock.now(),
                )
                return "dead"
            await self._store.mark_failed(
                record.id,
                str(exc),
                next_attempt_at=self._clock.now() + retry_delay(exc, record.attempts, self._rng),
                now=self._clock.now(),
            )
            return "failed"
        else:
            await self._store.mark_processed(record.id, self._clock.now())
            return "processed"

    async def replay(self, event_id: UUID) -> bool:
        """Put one dead-lettered event back into the queue."""
        return await self._store.replay(event_id, self._clock.now())
