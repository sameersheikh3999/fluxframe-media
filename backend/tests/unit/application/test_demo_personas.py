"""Tests for the synthetic persona generator.

The interesting one here is the calibration test. It generates a thousand
personas and checks that the *real* scorer places them roughly where the
generator intended. That closes a loop most demo-data code leaves open: without
it, a change to the scoring weights would silently turn "mostly hot" into a page
of warm leads, and nobody would notice until a demo.
"""

import random
from collections import Counter

import pytest

from app.application.demo.personas import build_persona
from app.application.dto.demo import DemoQuality, DemoScenario
from app.domain.leads.enums import Industry, LeadTemperature
from app.domain.leads.scoring import ScoringInput, classify, score_lead

pytestmark = pytest.mark.unit

SAMPLE = 1000


def score_of(persona: object) -> LeadTemperature:
    """Score a persona with the production scorer, not the generator's intent."""
    return classify(
        score_lead(
            ScoringInput(
                monthly_marketing_budget=persona.monthly_marketing_budget,  # type: ignore[attr-defined]
                content_volume=persona.content_volume,  # type: ignore[attr-defined]
                start_timeline=persona.start_timeline,  # type: ignore[attr-defined]
                primary_goal=persona.primary_goal,  # type: ignore[attr-defined]
                industry=persona.industry,  # type: ignore[attr-defined]
            )
        ).score
    )


def generate(
    count: int,
    quality: DemoQuality = DemoQuality.RANDOM,
    scenario: DemoScenario = DemoScenario.NORMAL_WEEK,
    industry: Industry | None = None,
    seed: int = 42,
) -> list[object]:
    rng = random.Random(seed)
    return [
        build_persona(rng, quality=quality, scenario=scenario, industry=industry, sequence=i)
        for i in range(count)
    ]


# --- safety -----------------------------------------------------------------


def test_every_generated_email_is_example_com() -> None:
    """Non-negotiable. @example.com is RFC 2606 reserved and can never route.

    Generating plausible Gmail addresses would mean writing real people's
    addresses into a CRM.
    """
    for persona in generate(200):
        assert persona.email.endswith("@example.com")  # type: ignore[attr-defined]


def test_generated_emails_are_unique_within_a_batch() -> None:
    emails = {p.email for p in generate(50)}  # type: ignore[attr-defined]
    assert len(emails) == 50


def test_websites_also_use_the_reserved_domain() -> None:
    for persona in generate(50):
        assert ".example.com" in persona.website  # type: ignore[attr-defined]


# --- coherence --------------------------------------------------------------


def test_personas_land_in_the_band_they_aimed_for() -> None:
    """The generator does not get to assert a temperature — it has to earn one
    from the same rules the production path uses."""
    personas = generate(300)
    agreement = sum(1 for p in personas if score_of(p) is p.intended_temperature)  # type: ignore[attr-defined]
    assert agreement / len(personas) > 0.97


def test_company_names_match_their_industry() -> None:
    """A dental practice should not be called "Iron Forge Gym"."""
    for persona in generate(60, industry=Industry.DENTAL):
        assert any(
            word in persona.company_name  # type: ignore[attr-defined]
            for word in ("Dental", "Orthodontics")
        )


def test_a_requested_industry_is_always_honoured() -> None:
    for persona in generate(40, industry=Industry.LEGAL):
        assert persona.industry is Industry.LEGAL  # type: ignore[attr-defined]


def test_hot_personas_carry_an_urgent_message() -> None:
    """The free text is what the Phase 6 AI brief reads, so it must carry real
    signal rather than lorem ipsum."""
    hot = [
        p
        for p in generate(200, quality=DemoQuality.MOSTLY_HOT)
        if p.intended_temperature is LeadTemperature.HOT  # type: ignore[attr-defined]
    ]
    assert hot
    for persona in hot[:20]:
        assert len(persona.message) > 60  # type: ignore[attr-defined]


# --- distribution calibration ----------------------------------------------


def test_the_default_mix_is_realistic() -> None:
    """Target: roughly 20% hot, 45% warm, 35% cold.

    Generous tolerances, because the point is to catch a scoring change that
    breaks the mix entirely, not to pin down exact ratios.
    """
    counts = Counter(score_of(p) for p in generate(SAMPLE))
    total = sum(counts.values())

    assert 0.12 <= counts[LeadTemperature.HOT] / total <= 0.30
    assert 0.33 <= counts[LeadTemperature.WARM] / total <= 0.58
    assert 0.22 <= counts[LeadTemperature.COLD] / total <= 0.48


@pytest.mark.parametrize(
    ("quality", "dominant"),
    [
        (DemoQuality.MOSTLY_HOT, LeadTemperature.HOT),
        (DemoQuality.MOSTLY_WARM, LeadTemperature.WARM),
        (DemoQuality.MOSTLY_COLD, LeadTemperature.COLD),
    ],
)
def test_quality_selection_actually_skews_the_output(
    quality: DemoQuality, dominant: LeadTemperature
) -> None:
    counts = Counter(score_of(p) for p in generate(SAMPLE, quality=quality))
    assert counts.most_common(1)[0][0] is dominant


def test_scenarios_set_both_quality_and_attribution() -> None:
    high = generate(200, scenario=DemoScenario.HIGH_INTENT_CAMPAIGN)
    low = generate(200, scenario=DemoScenario.LOW_QUALITY_CAMPAIGN)

    assert all(p.utm_source == "linkedin" for p in high)  # type: ignore[attr-defined]
    assert all(p.utm_campaign == "broad_awareness" for p in low)  # type: ignore[attr-defined]

    hot_high = sum(1 for p in high if score_of(p) is LeadTemperature.HOT)
    hot_low = sum(1 for p in low if score_of(p) is LeadTemperature.HOT)
    assert hot_high > hot_low


def test_the_generator_is_reproducible_given_a_seed() -> None:
    """Which is what makes the calibration tests above possible at all."""
    a = [p.email for p in generate(20, seed=7)]  # type: ignore[attr-defined]
    b = [p.email for p in generate(20, seed=7)]  # type: ignore[attr-defined]
    assert a == b


def test_different_seeds_produce_different_batches() -> None:
    a = [p.email for p in generate(20, seed=1)]  # type: ignore[attr-defined]
    b = [p.email for p in generate(20, seed=2)]  # type: ignore[attr-defined]
    assert a != b


def test_the_incoherent_combination_appears_in_cold_data() -> None:
    """Small budget + 20 videos a month exists on purpose, so the -10 coherence
    penalty is visible in demo data rather than only in tests."""
    from app.domain.leads.enums import ContentVolume, MarketingBudget

    personas = generate(SAMPLE, quality=DemoQuality.MOSTLY_COLD)
    assert any(
        p.monthly_marketing_budget is MarketingBudget.UNDER_2K  # type: ignore[attr-defined]
        and p.content_volume.min_videos >= 20  # type: ignore[attr-defined]
        for p in personas
    )
    assert ContentVolume.TWENTY.min_videos == 20
