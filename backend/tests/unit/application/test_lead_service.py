"""Unit tests for LeadService.

Everything here runs against `FakeUnitOfWork` — no database, no HTTP, no
framework. The fake genuinely stages and commits, so these tests can assert the
transaction semantics, not just the happy path.
"""

from datetime import UTC, datetime

import pytest

from app.application.dto.leads import AttributionCommand, CaptureLeadCommand
from app.application.errors import LeadNotFoundError
from app.application.services.lead_service import LeadService
from app.domain.leads.activities import ActivityType
from app.domain.leads.enums import (
    ContentVolume,
    Industry,
    LeadSource,
    LeadStatus,
    MarketingBudget,
    MonthlyRevenue,
    PrimaryGoal,
    StartTimeline,
)
from app.domain.leads.errors import IllegalLeadTransitionError
from tests.fakes import FakeUnitOfWork, FrozenClock

pytestmark = pytest.mark.unit

NOW = datetime(2026, 3, 1, 9, 30, tzinfo=UTC)


def make_command(key: str = "key-0001", **overrides: object) -> CaptureLeadCommand:
    defaults: dict[str, object] = {
        "idempotency_key": key,
        "first_name": "Sarah",
        "last_name": "Morgan",
        "email": "sarah@example.com",
        "company_name": "Bloom Skin Clinic",
        "industry": Industry.BEAUTY,
        "monthly_revenue": MonthlyRevenue.FROM_100K_TO_500K,
        "monthly_marketing_budget": MarketingBudget.OVER_10K,
        "content_volume": ContentVolume.THIRTY_PLUS,
        "primary_goal": PrimaryGoal.LEAD_GENERATION,
        "start_timeline": StartTimeline.IMMEDIATELY,
        "message": "New clinic opening in six weeks.",
        "source": LeadSource.WEBSITE,
        "attribution": AttributionCommand(utm_source="google"),
    }
    defaults.update(overrides)
    return CaptureLeadCommand(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def service(uow: FakeUnitOfWork) -> LeadService:
    return LeadService(uow=uow, clock=FrozenClock(NOW))


# --- capture ----------------------------------------------------------------


async def test_capture_stores_a_scored_lead(service: LeadService, uow: FakeUnitOfWork) -> None:
    result = await service.capture_lead(make_command())

    lead = uow.leads_store[result.id]
    assert lead.score == 100
    assert lead.temperature is not None
    assert lead.created_at == NOW
    assert result.was_duplicate is False


async def test_capture_commits_exactly_once(service: LeadService, uow: FakeUnitOfWork) -> None:
    """One lead, one transaction."""
    await service.capture_lead(make_command())
    assert uow.commits == 1


async def test_lead_activity_and_outbox_event_are_written_together(
    service: LeadService, uow: FakeUnitOfWork
) -> None:
    """THE invariant.

    All three writes land in the same commit. If the lead were committed first
    and the outbox row second, a crash in between would leave a lead HubSpot
    never hears about — silently, and forever.
    """
    result = await service.capture_lead(make_command())

    assert result.id in uow.leads_store
    assert [a.lead_id for a in uow.activities_store] == [result.id, result.id]
    assert "LeadCaptured" in uow.event_types()
    # Everything arrived in a single commit.
    assert uow.commits == 1


async def test_nothing_is_written_when_the_transaction_never_commits(
    uow: FakeUnitOfWork,
) -> None:
    """A failure partway through must leave no partial write.

    Simulated by making the domain reject the data: `Lead.capture` raises after
    the unit of work is entered but before `commit()`.
    """
    service = LeadService(uow=uow, clock=FrozenClock(NOW))

    with pytest.raises(Exception):  # noqa: B017 - InvalidLeadDataError
        await service.capture_lead(make_command(first_name="   "))

    assert uow.leads_store == {}
    assert uow.activities_store == []
    assert uow.outbox_store == []
    assert uow.commits == 0


async def test_a_hot_lead_emits_both_events(service: LeadService, uow: FakeUnitOfWork) -> None:
    await service.capture_lead(make_command())
    assert set(uow.event_types()) == {"LeadCaptured", "LeadMarkedHot"}


async def test_the_correlation_id_is_carried_onto_every_event(
    service: LeadService, uow: FakeUnitOfWork
) -> None:
    """So a HubSpot call made ten seconds later traces back to the web request."""
    await service.capture_lead(make_command(), correlation_id="req-abc-123")
    assert all(cid == "req-abc-123" for _, cid in uow.outbox_store)


async def test_capture_records_both_a_captured_and_a_scored_activity(
    service: LeadService, uow: FakeUnitOfWork
) -> None:
    await service.capture_lead(make_command())
    types = {a.activity_type for a in uow.activities_store}
    assert types == {ActivityType.CAPTURED, ActivityType.SCORED}


async def test_a_demo_lead_is_attributed_to_the_generator(
    service: LeadService, uow: FakeUnitOfWork
) -> None:
    await service.capture_lead(make_command(is_demo=True, source=LeadSource.DEMO_GENERATOR))
    captured = next(a for a in uow.activities_store if a.activity_type is ActivityType.CAPTURED)
    assert captured.actor == "demo_generator"


# --- idempotency ------------------------------------------------------------


async def test_the_same_key_twice_creates_one_lead(
    service: LeadService, uow: FakeUnitOfWork
) -> None:
    """The double-click case, which is the one that actually happens."""
    first = await service.capture_lead(make_command(key="same-key"))
    second = await service.capture_lead(make_command(key="same-key"))

    assert first.id == second.id
    assert second.was_duplicate is True
    assert len(uow.leads_store) == 1


async def test_a_replay_writes_no_second_outbox_event(
    service: LeadService, uow: FakeUnitOfWork
) -> None:
    """Otherwise a double-click would create two HubSpot contacts."""
    await service.capture_lead(make_command(key="same-key"))
    events_after_first = len(uow.outbox_store)

    await service.capture_lead(make_command(key="same-key"))

    assert len(uow.outbox_store) == events_after_first


async def test_a_replay_does_not_commit(service: LeadService, uow: FakeUnitOfWork) -> None:
    await service.capture_lead(make_command(key="same-key"))
    await service.capture_lead(make_command(key="same-key"))
    assert uow.commits == 1


async def test_different_keys_create_different_leads(
    service: LeadService, uow: FakeUnitOfWork
) -> None:
    """Email is deliberately not unique: a genuine re-enquiry is a new lead."""
    a = await service.capture_lead(make_command(key="key-a"))
    b = await service.capture_lead(make_command(key="key-b"))

    assert a.id != b.id
    assert len(uow.leads_store) == 2


# --- lifecycle transitions --------------------------------------------------


async def test_transition_updates_status_and_logs_it(
    service: LeadService, uow: FakeUnitOfWork
) -> None:
    result = await service.capture_lead(make_command())

    await service.transition_status(result.id, LeadStatus.QUALIFIED, actor="user:sam")

    assert uow.leads_store[result.id].status is LeadStatus.QUALIFIED
    change = next(a for a in uow.activities_store if a.activity_type is ActivityType.STATUS_CHANGED)
    assert change.actor == "user:sam"


async def test_an_illegal_transition_raises_and_writes_nothing(
    service: LeadService, uow: FakeUnitOfWork
) -> None:
    """The rule lives in the entity, so every caller is constrained equally."""
    result = await service.capture_lead(make_command())
    commits_before = uow.commits
    activities_before = len(uow.activities_store)

    with pytest.raises(IllegalLeadTransitionError):
        await service.transition_status(result.id, LeadStatus.WON, actor="user:sam")

    assert uow.leads_store[result.id].status is LeadStatus.NEW
    assert uow.commits == commits_before
    assert len(uow.activities_store) == activities_before


async def test_transitioning_a_missing_lead_raises_not_found(
    service: LeadService,
) -> None:
    from uuid import uuid4

    with pytest.raises(LeadNotFoundError):
        await service.transition_status(uuid4(), LeadStatus.QUALIFIED, actor="x")


# --- rescoring --------------------------------------------------------------


async def test_rescore_recomputes_and_logs(service: LeadService, uow: FakeUnitOfWork) -> None:
    result = await service.capture_lead(make_command())
    score = await service.rescore_lead(result.id)

    assert score == 100
    scored = [a for a in uow.activities_store if a.activity_type is ActivityType.SCORED]
    assert len(scored) == 2  # one at capture, one at rescore


async def test_allowed_next_statuses_comes_from_the_domain() -> None:
    """The dashboard asks the domain which buttons to render, so it cannot offer
    a transition the entity would reject."""
    assert LeadService.allowed_next_statuses(LeadStatus.WON) == ()
    assert "qualified" in LeadService.allowed_next_statuses(LeadStatus.NEW)
