"""The background outbox worker.

An `asyncio` task started in the FastAPI lifespan that polls the outbox every
few seconds. Deliberately the simplest thing that is actually correct:

* No Redis, no Celery, no external broker. The queue is a PostgreSQL table, so
  enqueueing an event is atomic with the business write that caused it — a
  guarantee no broker can offer, because a broker is a second system.
* Safe with multiple Railway replicas, because `claim_batch` uses
  `FOR UPDATE SKIP LOCKED`. Two workers polling the same table never receive
  the same event.
* Never crashes the application. A failure inside the loop is logged and the
  loop continues; the dispatcher's own retry policy handles per-event failures.

When would this stop being enough? When you need sub-second delivery (add
PostgreSQL LISTEN/NOTIFY to wake the poller, which costs almost nothing and no
new infrastructure), or when the dispatcher's work starts competing with request
handling for CPU (move it to its own Railway service reading the same database —
a deployment change, not a rewrite, precisely because it talks to the rest of
the system through ports).
"""

import asyncio
import contextlib

from app.application.services.outbox_dispatcher import OutboxDispatcher
from app.observability.logging import get_logger

_logger = get_logger(__name__)


class OutboxWorker:
    """Runs `dispatch_once` on a loop, in the background."""

    def __init__(
        self,
        *,
        dispatcher: OutboxDispatcher,
        poll_interval_seconds: float,
    ) -> None:
        self._dispatcher = dispatcher
        self._interval = poll_interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run(), name="outbox-dispatcher")
        _logger.info("outbox_worker_started", poll_interval=self._interval)

    async def stop(self) -> None:
        """Ask the loop to finish, then wait briefly for it.

        Cancelling mid-delivery is safe: the claimed row stays `processing` and
        `reclaim_stalled` returns it to the queue a few minutes later. Handlers
        are idempotent, so redelivery costs nothing.
        """
        if self._task is None:
            return
        self._stopping.set()
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        _logger.info("outbox_worker_stopped")

    async def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                report = await self._dispatcher.dispatch_once()
                if report.claimed:
                    _logger.info(
                        "outbox_batch_dispatched",
                        claimed=report.claimed,
                        processed=report.processed,
                        failed=report.failed,
                        dead_lettered=report.dead_lettered,
                        skipped=report.skipped,
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                # A failure here means something structural (the database is
                # unreachable, a handler raised outside its own error handling).
                # Log it and keep polling: an outbox worker that dies on the
                # first bad minute is worse than one that retries.
                _logger.exception("outbox_worker_iteration_failed")

            # Interruptible sleep: shutdown does not wait out a full interval.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=self._interval)
