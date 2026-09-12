"""Unit tests for the Lead aggregate and its lifecycle.

No database, no framework, no fixtures. If these ever need one, a business rule
has leaked into infrastructure.
"""

from datetime import UTC, datetime

import pytest

from app.domain.leads.entities import (
    Attribution,
    ContactDetails,
    Lead,
    QualificationAnswers,
)
from app.domain.leads.enums import (
    ContentVolume,
    CrmSyncStatus,
    Industry,
    LeadSource,
    LeadStatus,
    LeadTemperature,
    MarketingBudget,
    MonthlyRevenue,
    PrimaryGoal,
    StartTimeline,
)
from app.domain.leads.errors import IllegalLeadTransitionError, InvalidLeadDataError
from app.domain.leads.events import LeadCaptured, LeadMarkedHot, LeadStatusChanged
from app.domain.leads.lifecycle import ALLOWED_TRANSITIONS, TERMINAL_STATUSES

pytestmark = pytest.mark.unit

NOW = datetime(2026, 3, 1, 9, 30, tzinfo=UTC)
LATER = datetime(2026, 3, 2, 9, 30, tzinfo=UTC)


def make_lead(
    budget: MarketingBudget = MarketingBudget.OVER_10K,
    volume: ContentVolume = ContentVolume.THIRTY_PLUS,
    timeline: StartTimeline = StartTimeline.IMMEDIATELY,
    goal: PrimaryGoal = PrimaryGoal.LEAD_GENERATION,
    industry: Industry = Industry.DENTAL,
    key: str = "key-0001",
) -> Lead:
    return Lead.capture(
        idempotency_key=key,
        contact=ContactDetails(
            first_name="Sarah",
            last_name="Morgan",
            email="sarah@example.com",
            company_name="Bloom Skin Clinic",
        ),
        answers=QualificationAnswers(
            industry=industry,
            monthly_revenue=MonthlyRevenue.FROM_100K_TO_500K,
            monthly_marketing_budget=budget,
            content_volume=volume,
            primary_goal=goal,
            start_timeline=timeline,
            message="We need help.",
        ),
        attribution=Attribution(utm_source="google"),
        source=LeadSource.WEBSITE,
        now=NOW,
    )


# --- capture ----------------------------------------------------------------


def test_capture_scores_the_lead_immediately() -> None:
    """Scoring is part of capturing, not a later step a caller might forget."""
    lead = make_lead()
    assert lead.score == 100
    assert lead.temperature is LeadTemperature.HOT
    assert lead.score_version == "v1"
    assert lead.score_breakdown is not None


def test_capture_starts_in_new_with_a_pending_sync() -> None:
    lead = make_lead()
    assert lead.status is LeadStatus.NEW
    assert lead.crm_sync_status is CrmSyncStatus.PENDING
    assert lead.crm_contact_id is None


def test_capture_uses_the_supplied_time_not_the_wall_clock() -> None:
    """The domain performs no I/O, and reading the clock is I/O."""
    lead = make_lead()
    assert lead.created_at == NOW
    assert lead.updated_at == NOW


def test_capture_emits_lead_captured() -> None:
    events = make_lead().collect_events()
    assert any(isinstance(e, LeadCaptured) for e in events)
    captured = next(e for e in events if isinstance(e, LeadCaptured))
    assert captured.payload["email"] == "sarah@example.com"
    assert captured.payload["temperature"] == "hot"


def test_a_hot_lead_also_emits_lead_marked_hot() -> None:
    """A separate event because the interesting consumers differ: this is what
    a 'notify sales now' handler subscribes to."""
    assert any(isinstance(e, LeadMarkedHot) for e in make_lead().collect_events())


def test_a_cold_lead_does_not_emit_lead_marked_hot() -> None:
    cold = make_lead(
        budget=MarketingBudget.UNDER_2K,
        volume=ContentVolume.FOUR,
        timeline=StartTimeline.RESEARCHING,
        goal=PrimaryGoal.SOCIAL_GROWTH,
        industry=Industry.RESTAURANT,
    )
    assert cold.temperature is LeadTemperature.COLD
    assert not any(isinstance(e, LeadMarkedHot) for e in cold.collect_events())


def test_collecting_events_drains_them() -> None:
    """Draining prevents the same event being written to the outbox twice."""
    lead = make_lead()
    assert lead.collect_events()
    assert lead.collect_events() == []


# --- business validation ----------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("first_name", "   "),
        ("last_name", ""),
        ("email", "not-an-email"),
        ("company_name", "  "),
    ],
)
def test_capture_rejects_meaningless_contact_details(field: str, value: str) -> None:
    """Business validation, distinct from Pydantic's transport validation.

    This runs no matter who called: HTTP, a worker, the demo generator, or a
    future agent.
    """
    contact_fields = {
        "first_name": "Sarah",
        "last_name": "Morgan",
        "email": "sarah@example.com",
        "company_name": "Bloom",
    }
    contact_fields[field] = value

    with pytest.raises(InvalidLeadDataError):
        Lead.capture(
            idempotency_key="k",
            contact=ContactDetails(**contact_fields),
            answers=QualificationAnswers(
                industry=Industry.DENTAL,
                monthly_revenue=MonthlyRevenue.UNDER_50K,
                monthly_marketing_budget=MarketingBudget.UNDER_2K,
                content_volume=ContentVolume.FOUR,
                primary_goal=PrimaryGoal.SALES,
                start_timeline=StartTimeline.RESEARCHING,
            ),
            attribution=Attribution(),
            source=LeadSource.WEBSITE,
            now=NOW,
        )


def test_capture_requires_an_idempotency_key() -> None:
    with pytest.raises(InvalidLeadDataError):
        make_lead(key="   ")


# --- lifecycle --------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "target"),
    [
        (LeadStatus.NEW, LeadStatus.QUALIFIED),
        (LeadStatus.NEW, LeadStatus.CONTACTED),
        (LeadStatus.NEW, LeadStatus.DISQUALIFIED),
        (LeadStatus.QUALIFIED, LeadStatus.BOOKED),
        (LeadStatus.CONTACTED, LeadStatus.BOOKED),
        (LeadStatus.BOOKED, LeadStatus.WON),
        (LeadStatus.BOOKED, LeadStatus.LOST),
    ],
)
def test_legal_transitions_are_allowed(start: LeadStatus, target: LeadStatus) -> None:
    lead = make_lead()
    lead.status = start
    lead.transition_to(target, LATER)
    assert lead.status is target


@pytest.mark.parametrize(
    ("start", "target"),
    [
        (LeadStatus.WON, LeadStatus.NEW),  # the headline case
        (LeadStatus.NEW, LeadStatus.WON),  # cannot skip the pipeline
        (LeadStatus.NEW, LeadStatus.BOOKED),
        (LeadStatus.LOST, LeadStatus.QUALIFIED),
        (LeadStatus.DISQUALIFIED, LeadStatus.CONTACTED),
        (LeadStatus.CONTACTED, LeadStatus.QUALIFIED),  # no going backwards
    ],
)
def test_illegal_transitions_are_rejected(start: LeadStatus, target: LeadStatus) -> None:
    lead = make_lead()
    lead.status = start
    with pytest.raises(IllegalLeadTransitionError):
        lead.transition_to(target, LATER)
    assert lead.status is start  # unchanged


def test_terminal_statuses_have_no_exits() -> None:
    for status in TERMINAL_STATUSES:
        assert ALLOWED_TRANSITIONS[status] == frozenset()


def test_every_status_appears_in_the_transition_table() -> None:
    """A new status with no table entry would raise KeyError at runtime."""
    assert set(ALLOWED_TRANSITIONS) == set(LeadStatus)


def test_transitioning_to_the_current_status_is_a_no_op() -> None:
    """Idempotent: clicking 'Qualified' twice must not error or double-log."""
    lead = make_lead()
    lead.transition_to(LeadStatus.QUALIFIED, LATER)
    lead.collect_events()
    lead.transition_to(LeadStatus.QUALIFIED, LATER)
    assert lead.collect_events() == []


def test_a_transition_emits_lead_status_changed() -> None:
    lead = make_lead()
    lead.collect_events()
    lead.transition_to(LeadStatus.QUALIFIED, LATER)
    events = lead.collect_events()
    assert len(events) == 1
    assert isinstance(events[0], LeadStatusChanged)
    assert events[0].payload == {
        "lead_id": str(lead.id),
        "from_status": "new",
        "to_status": "qualified",
    }


def test_status_is_independent_of_temperature() -> None:
    """Re-scoring must never move a lead through the sales pipeline.

    Temperature is a model output; status records what a human actually did.
    Conflating them means a scoring change rewrites sales history.
    """
    lead = make_lead()
    lead.transition_to(LeadStatus.QUALIFIED, LATER)
    lead.rescore(LATER)
    assert lead.status is LeadStatus.QUALIFIED


# --- CRM state --------------------------------------------------------------


def test_marking_synced_records_the_contact_and_clears_the_error() -> None:
    lead = make_lead()
    lead.mark_crm_failed("boom", LATER)
    lead.mark_crm_synced("hs-123", LATER)
    assert lead.crm_sync_status is CrmSyncStatus.SYNCED
    assert lead.crm_contact_id == "hs-123"
    assert lead.crm_sync_error is None


def test_marking_failed_increments_the_attempt_counter() -> None:
    lead = make_lead()
    lead.mark_crm_failed("timeout", LATER)
    lead.mark_crm_failed("timeout", LATER)
    assert lead.crm_sync_attempts == 2
    assert lead.crm_sync_status is CrmSyncStatus.FAILED


def test_error_text_is_truncated_before_storage() -> None:
    """Error strings reach the database and the dashboard; unbounded ones are a
    storage and rendering problem."""
    lead = make_lead()
    lead.mark_crm_failed("x" * 5000, LATER)
    assert lead.crm_sync_error is not None
    assert len(lead.crm_sync_error) <= 1000
