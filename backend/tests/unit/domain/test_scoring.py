"""Unit tests for the deterministic scoring engine.

The most valuable tests in the codebase, and the cheapest: no database, no
network, no fixtures, no framework. Scoring is a pure function, so testing it is
just calling it.
"""

import pytest

from app.domain.leads.enums import (
    ContentVolume,
    Industry,
    LeadTemperature,
    MarketingBudget,
    PrimaryGoal,
    StartTimeline,
)
from app.domain.leads.scoring import (
    BUDGET_POINTS,
    GOAL_POINTS,
    HOT_THRESHOLD,
    INCOHERENT_BUDGET_VOLUME_PENALTY,
    INDUSTRY_POINTS,
    MAX_SCORE,
    MIN_SCORE,
    SCORING_VERSION,
    TIMELINE_POINTS,
    VOLUME_POINTS,
    WARM_THRESHOLD,
    ScoringInput,
    classify,
    score_lead,
)

pytestmark = pytest.mark.unit


def make_input(
    budget: MarketingBudget = MarketingBudget.FROM_2K_TO_5K,
    volume: ContentVolume = ContentVolume.EIGHT,
    timeline: StartTimeline = StartTimeline.ONE_TO_THREE_MONTHS,
    goal: PrimaryGoal = PrimaryGoal.BRAND_AWARENESS,
    industry: Industry = Industry.OTHER,
) -> ScoringInput:
    return ScoringInput(
        monthly_marketing_budget=budget,
        content_volume=volume,
        start_timeline=timeline,
        primary_goal=goal,
        industry=industry,
    )


# --- the weight tables ------------------------------------------------------


def test_every_enum_member_has_a_weight() -> None:
    """A new enum member with no weight would raise KeyError at runtime.

    Cheap insurance against the most likely future edit to this module.
    """
    assert set(BUDGET_POINTS) == set(MarketingBudget)
    assert set(VOLUME_POINTS) == set(ContentVolume)
    assert set(TIMELINE_POINTS) == set(StartTimeline)
    assert set(GOAL_POINTS) == set(PrimaryGoal)
    assert set(INDUSTRY_POINTS) == set(Industry)


def test_the_dimensions_sum_to_exactly_one_hundred() -> None:
    """30 + 20 + 20 + 15 + 15 = 100.

    This is what makes 0-100 a meaningful range rather than an arbitrary one,
    and makes the clamp a safety net rather than a routine occurrence. If a
    weight is ever raised without lowering another, this test says so.
    """
    best = (
        max(BUDGET_POINTS.values())
        + max(VOLUME_POINTS.values())
        + max(TIMELINE_POINTS.values())
        + max(GOAL_POINTS.values())
        + max(INDUSTRY_POINTS.values())
    )
    assert best == MAX_SCORE


def test_weights_are_immutable() -> None:
    """MappingProxyType means a caller cannot quietly rewrite the rules."""
    with pytest.raises(TypeError):
        BUDGET_POINTS[MarketingBudget.UNDER_2K] = 999  # type: ignore[index]


# --- the perfect and the hopeless -------------------------------------------


def test_a_perfect_lead_scores_one_hundred_and_is_hot() -> None:
    result = score_lead(
        make_input(
            budget=MarketingBudget.OVER_10K,
            volume=ContentVolume.THIRTY_PLUS,
            timeline=StartTimeline.IMMEDIATELY,
            goal=PrimaryGoal.LEAD_GENERATION,
            industry=Industry.DENTAL,
        )
    )
    assert result.score == 100
    assert result.temperature is LeadTemperature.HOT
    assert result.was_clamped is False


def test_the_weakest_possible_lead_is_cold_and_still_in_range() -> None:
    result = score_lead(
        make_input(
            budget=MarketingBudget.UNDER_2K,
            volume=ContentVolume.FOUR,
            timeline=StartTimeline.RESEARCHING,
            goal=PrimaryGoal.SOCIAL_GROWTH,
            industry=Industry.RESTAURANT,
        )
    )
    assert MIN_SCORE <= result.score <= MAX_SCORE
    assert result.temperature is LeadTemperature.COLD


# --- classification boundaries ----------------------------------------------


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0, LeadTemperature.COLD),
        (49, LeadTemperature.COLD),
        (50, LeadTemperature.WARM),  # boundary
        (79, LeadTemperature.WARM),
        (80, LeadTemperature.HOT),  # boundary
        (100, LeadTemperature.HOT),
    ],
)
def test_classification_boundaries(score: int, expected: LeadTemperature) -> None:
    """The two boundaries are where off-by-one bugs live."""
    assert classify(score) is expected


def test_thresholds_are_the_documented_values() -> None:
    assert WARM_THRESHOLD == 50
    assert HOT_THRESHOLD == 80


# --- the coherence penalty --------------------------------------------------


def test_small_budget_with_industrial_volume_is_penalised() -> None:
    """A sub-2k budget asking for 20+ videos a month has not costed the work."""
    penalised = score_lead(make_input(budget=MarketingBudget.UNDER_2K, volume=ContentVolume.TWENTY))
    unpenalised = score_lead(
        make_input(budget=MarketingBudget.FROM_2K_TO_5K, volume=ContentVolume.TWENTY)
    )

    dimensions = {c.dimension for c in penalised.components}
    assert "coherence_penalty" in dimensions
    assert "coherence_penalty" not in {c.dimension for c in unpenalised.components}

    penalty = next(c for c in penalised.components if c.dimension == "coherence_penalty")
    assert penalty.points == INCOHERENT_BUDGET_VOLUME_PENALTY == -10


@pytest.mark.parametrize(
    ("volume", "should_penalise"),
    [
        (ContentVolume.FOUR, False),
        (ContentVolume.EIGHT, False),
        (ContentVolume.TWELVE, False),
        (ContentVolume.TWENTY, True),  # boundary: >= 20
        (ContentVolume.THIRTY_PLUS, True),
    ],
)
def test_penalty_boundary_is_twenty_videos(volume: ContentVolume, should_penalise: bool) -> None:
    """Proves the rule reads the enum's `min_videos`, not its string value.

    A string comparison would sort "4" above "20" and get this exactly wrong.
    """
    result = score_lead(make_input(budget=MarketingBudget.UNDER_2K, volume=volume))
    has_penalty = any(c.dimension == "coherence_penalty" for c in result.components)
    assert has_penalty is should_penalise


# --- the breakdown ----------------------------------------------------------


def test_components_sum_to_the_raw_total() -> None:
    """The explanation must actually add up to the number it explains."""
    result = score_lead(
        make_input(budget=MarketingBudget.UNDER_2K, volume=ContentVolume.THIRTY_PLUS)
    )
    assert sum(c.points for c in result.components) == result.raw_total


def test_breakdown_is_json_serialisable_and_self_describing() -> None:
    """It goes into a JSONB column and must stay readable years later."""
    import json

    result = score_lead(make_input())
    breakdown = result.to_breakdown()

    # Round-trips through JSON with no custom encoder: plain dicts and lists.
    assert json.loads(json.dumps(breakdown)) == breakdown
    assert breakdown["version"] == SCORING_VERSION
    assert breakdown["final_score"] == result.score
    assert len(breakdown["components"]) == len(result.components)  # type: ignore[arg-type]


def test_every_component_carries_a_human_readable_reason() -> None:
    """ "Why did this lead score 87?" has to be answerable without the code."""
    result = score_lead(make_input())
    for component in result.components:
        assert component.reason
        assert component.input_value


def test_scoring_is_deterministic() -> None:
    """Same input, same output, forever. This is what makes a stored breakdown
    trustworthy six months after the fact."""
    data = make_input(budget=MarketingBudget.FROM_5K_TO_10K)
    assert score_lead(data).to_breakdown() == score_lead(data).to_breakdown()


def test_score_is_always_clamped_into_range() -> None:
    """Exhaustive: every possible combination stays within 0-100."""
    for budget in MarketingBudget:
        for volume in ContentVolume:
            for timeline in StartTimeline:
                for goal in PrimaryGoal:
                    for industry in Industry:
                        result = score_lead(make_input(budget, volume, timeline, goal, industry))
                        assert MIN_SCORE <= result.score <= MAX_SCORE
