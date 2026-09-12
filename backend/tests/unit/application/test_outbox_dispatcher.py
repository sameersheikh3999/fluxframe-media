"""Unit tests for the outbox dispatcher's retry policy.

This is the reliability core, and its behaviour is entirely about *classifying*
failures. These tests pin down the four outcomes — processed, retried,
dead-lettered, skipped — without any database or network.
"""

import random
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application.errors import CrmPermanentError, CrmTransientError
from app.application.ports.outbox_store import OutboxRecord
from app.application.services.outbox_dispatcher import (
    MAX_BACKOFF_SECONDS,
    OutboxDispatcher,
    compute_backoff,
    retry_delay,
)
from tests.fakes import (
    FrozenClock,
    InMemoryOutboxStore,
    RecordingHandler,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def make_record(event_type: str = "LeadCaptured", attempts: int = 1) -> OutboxRecord:
    lead_id = uuid4()
    return OutboxRecord(
        id=uuid4(),
        event_type=event_type,
        event_version=1,
        aggregate_type="lead",
        aggregate_id=lead_id,
        payload={"lead_id": str(lead_id)},
        correlation_id="req-1",
        attempts=attempts,
        occurred_at=NOW,
    )


def make_dispatcher(
    store: InMemoryOutboxStore,
    handler: RecordingHandler | None = None,
    *,
    max_attempts: int = 6,
) -> OutboxDispatcher:
    handlers = {"LeadCaptured": handler} if handler else {}
    return OutboxDispatcher(
        store=store,
        handlers=handlers,  # type: ignore[arg-type]
        clock=FrozenClock(NOW),
        max_attempts=max_attempts,
        rng=random.Random(1234),
    )


# --- the four outcomes ------------------------------------------------------


async def test_a_successful_delivery_is_marked_processed() -> None:
    record = make_record()
    store = InMemoryOutboxStore([record])
    handler = RecordingHandler()

    report = await make_dispatcher(store, handler).dispatch_once()

    assert report.processed == 1
    assert store.processed == [record.id]
    assert handler.handled == [record]


async def test_a_transient_failure_is_retried_not_dead_lettered() -> None:
    """HubSpot having a bad minute must not lose the event."""
    record = make_record(attempts=1)
    store = InMemoryOutboxStore([record])
    handler = RecordingHandler(fail_with=CrmTransientError("503 from HubSpot"))

    report = await make_dispatcher(store, handler).dispatch_once()

    assert report.failed == 1
    assert report.dead_lettered == 0
    assert len(store.failed) == 1
    _, error, next_attempt = store.failed[0]
    assert "503" in error
    assert next_attempt > NOW  # scheduled for later


async def test_a_permanent_failure_dead_letters_immediately() -> None:
    """A 400 for a missing custom property will never succeed on retry.

    Retrying it forever hides a configuration bug behind a queue that quietly
    grows; dead-lettering surfaces it on the dashboard.
    """
    record = make_record(attempts=1)
    store = InMemoryOutboxStore([record])
    handler = RecordingHandler(fail_with=CrmPermanentError("Unknown property"))

    report = await make_dispatcher(store, handler).dispatch_once()

    assert report.dead_lettered == 1
    assert report.failed == 0
    assert store.dead[0][0] == record.id


async def test_exhausted_attempts_dead_letter_even_when_transient() -> None:
    record = make_record(attempts=6)
    store = InMemoryOutboxStore([record])
    handler = RecordingHandler(fail_with=CrmTransientError("still down"))

    report = await make_dispatcher(store, handler, max_attempts=6).dispatch_once()

    assert report.dead_lettered == 1
    assert "Giving up after 6 attempts" in store.dead[0][1]


async def test_an_event_with_no_handler_is_skipped_not_failed() -> None:
    """LeadMarkedHot has no consumer yet. That is not an error — the event is
    the historical record, and a consumer can be added later."""
    store = InMemoryOutboxStore([make_record(event_type="LeadMarkedHot")])

    report = await make_dispatcher(store, RecordingHandler()).dispatch_once()

    assert report.skipped == 1
    assert report.failed == 0
    assert len(store.processed) == 1


async def test_an_unexpected_exception_is_treated_as_transient() -> None:
    """Optimism is the safer default: a genuine bug still dead-letters after
    max_attempts, whereas treating unknowns as permanent would drop recoverable
    work on the first blip."""
    store = InMemoryOutboxStore([make_record(attempts=1)])
    handler = RecordingHandler(fail_with=RuntimeError("something odd"))

    report = await make_dispatcher(store, handler).dispatch_once()

    assert report.failed == 1
    assert report.dead_lettered == 0


# --- housekeeping -----------------------------------------------------------


async def test_every_pass_reclaims_stalled_rows_first() -> None:
    """A worker that died mid-delivery leaves rows marked `processing` forever.

    Safe to reclaim because every handler is idempotent.
    """
    store = InMemoryOutboxStore([])
    await make_dispatcher(store).dispatch_once()
    assert store.reclaimed == 1


async def test_an_empty_queue_is_a_no_op() -> None:
    report = await make_dispatcher(InMemoryOutboxStore([])).dispatch_once()
    assert report == type(report)(claimed=0, processed=0, failed=0, dead_lettered=0, skipped=0)


async def test_replay_delegates_to_the_store() -> None:
    store = InMemoryOutboxStore([])
    event_id = uuid4()
    assert await make_dispatcher(store).replay(event_id) is True
    assert store.replayed == [event_id]


# --- backoff ----------------------------------------------------------------


def test_backoff_grows_with_attempts() -> None:
    rng = random.Random(7)
    first = compute_backoff(1, rng).total_seconds()
    fifth = compute_backoff(5, rng).total_seconds()
    assert fifth > first


def test_backoff_is_capped() -> None:
    """A long-dead integration should still retry hourly, not drift to never."""
    delay = compute_backoff(50, random.Random(1)).total_seconds()
    assert delay <= MAX_BACKOFF_SECONDS


def test_backoff_is_jittered() -> None:
    """Without jitter, a thousand events that failed during one outage all
    retry at the same instant and re-create the outage."""
    rng = random.Random(99)
    delays = {compute_backoff(4, rng).total_seconds() for _ in range(20)}
    assert len(delays) > 1


def test_a_provider_supplied_retry_after_wins() -> None:
    """Retrying sooner than a rate limiter asked turns a short throttle into a
    long one."""
    exc = CrmTransientError("429", retry_after_seconds=120)
    assert retry_delay(exc, attempts=1, rng=random.Random(1)).total_seconds() == 120


def test_without_retry_after_the_backoff_curve_is_used() -> None:
    exc = CrmTransientError("500")
    delay = retry_delay(exc, attempts=3, rng=random.Random(1)).total_seconds()
    assert 0 < delay <= 8
