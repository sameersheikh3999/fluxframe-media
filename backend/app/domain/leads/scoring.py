"""Deterministic lead scoring.

This is the most important module in the codebase, and it is a pure function.
No database, no network, no randomness, no clock. Given the same inputs it
returns the same score forever — which is what makes a stored breakdown
trustworthy six months later.

Design notes worth understanding:

1.  **Rules are data, not code.** The weights live in the mappings below rather
    than in a chain of `if` statements. Adding a rule is adding a row.

2.  **Weights are versioned in code, not in environment variables.** If an
    operator could change weights from a dashboard, a stored `score_breakdown`
    would stop being reproducible and "why did this lead score 87?" would become
    unanswerable. Changing weights means bumping SCORING_VERSION and shipping.

3.  **The dimensions sum to exactly 100 before penalties**
    (budget 30 + volume 20 + timeline 20 + goal 15 + industry 15). That makes
    0-100 a meaningful range rather than an arbitrary one, and makes the clamp a
    safety net rather than a routine occurrence.

4.  **No LLM.** Scoring is a business rule, and business rules must be stable and
    explainable. Phase 6 adds an LLM that interprets free text alongside this;
    it never replaces it.
"""

from dataclasses import dataclass
from types import MappingProxyType

from app.domain.leads.enums import (
    ContentVolume,
    Industry,
    LeadTemperature,
    MarketingBudget,
    PrimaryGoal,
    StartTimeline,
)

#: Bump whenever any weight or rule below changes. Persisted with every score so
#: historical results stay interpretable.
SCORING_VERSION = "v1"

HOT_THRESHOLD = 80
WARM_THRESHOLD = 50

MIN_SCORE = 0
MAX_SCORE = 100

# --- Dimension weights -------------------------------------------------------

BUDGET_POINTS = MappingProxyType(
    {
        MarketingBudget.OVER_10K: 30,
        MarketingBudget.FROM_5K_TO_10K: 25,
        MarketingBudget.FROM_2K_TO_5K: 15,
        MarketingBudget.UNDER_2K: 5,
    }
)

VOLUME_POINTS = MappingProxyType(
    {
        ContentVolume.THIRTY_PLUS: 20,
        ContentVolume.TWENTY: 18,
        ContentVolume.TWELVE: 12,
        ContentVolume.EIGHT: 8,
        ContentVolume.FOUR: 4,
    }
)

TIMELINE_POINTS = MappingProxyType(
    {
        StartTimeline.IMMEDIATELY: 20,
        StartTimeline.WITHIN_30_DAYS: 15,
        StartTimeline.ONE_TO_THREE_MONTHS: 8,
        StartTimeline.RESEARCHING: 2,
    }
)

GOAL_POINTS = MappingProxyType(
    {
        PrimaryGoal.LEAD_GENERATION: 15,
        PrimaryGoal.SALES: 15,
        PrimaryGoal.PRODUCT_LAUNCH: 10,
        PrimaryGoal.BRAND_AWARENESS: 8,
        PrimaryGoal.SOCIAL_GROWTH: 8,
    }
)

#: Industry fit: how well Fluxframe's short-form playbook is known to work in
#: this vertical. High-ticket local services with visual before/after results
#: convert best. OTHER scores mid, so an unlisted industry is never punished for
#: being unlisted.
INDUSTRY_POINTS = MappingProxyType(
    {
        Industry.DENTAL: 15,
        Industry.BEAUTY: 15,
        Industry.REAL_ESTATE: 13,
        Industry.FITNESS: 12,
        Industry.PHYSIOTHERAPY: 12,
        Industry.LEGAL: 10,
        Industry.ECOMMERCE: 10,
        Industry.SAAS: 8,
        Industry.RESTAURANT: 7,
        Industry.OTHER: 8,
    }
)

# --- Penalties ---------------------------------------------------------------

#: A prospect on the smallest budget band asking for 20+ videos a month has not
#: costed the work. That combination predicts a difficult sale and a difficult
#: client, so it is penalised even though each answer scores well alone.
INCOHERENT_BUDGET_VOLUME_PENALTY = -10
INCOHERENT_VOLUME_THRESHOLD = 20


@dataclass(frozen=True, slots=True)
class ScoreComponent:
    """One line of the explanation for a score."""

    dimension: str
    input_value: str
    points: int
    reason: str


@dataclass(frozen=True, slots=True)
class ScoringInput:
    """Exactly the fields scoring depends on, and nothing else.

    A narrow input type keeps the function honest: it cannot start quietly
    depending on the email address or the company name.
    """

    monthly_marketing_budget: MarketingBudget
    content_volume: ContentVolume
    start_timeline: StartTimeline
    primary_goal: PrimaryGoal
    industry: Industry


@dataclass(frozen=True, slots=True)
class ScoreResult:
    """A score, plus everything needed to explain it later."""

    score: int
    temperature: LeadTemperature
    version: str
    components: tuple[ScoreComponent, ...]
    raw_total: int

    @property
    def was_clamped(self) -> bool:
        return self.raw_total != self.score

    def to_breakdown(self) -> dict[str, object]:
        """A JSON-serialisable explanation, persisted on the lead.

        Plain dicts and lists only. This crosses into a JSONB column, and the
        domain does not import a serialisation library to get there.
        """
        return {
            "version": self.version,
            "raw_total": self.raw_total,
            "final_score": self.score,
            "temperature": self.temperature.value,
            "was_clamped": self.was_clamped,
            "components": [
                {
                    "dimension": component.dimension,
                    "input_value": component.input_value,
                    "points": component.points,
                    "reason": component.reason,
                }
                for component in self.components
            ],
        }


def classify(score: int) -> LeadTemperature:
    """Bucket a 0-100 score. 80-100 HOT, 50-79 WARM, 0-49 COLD."""
    if score >= HOT_THRESHOLD:
        return LeadTemperature.HOT
    if score >= WARM_THRESHOLD:
        return LeadTemperature.WARM
    return LeadTemperature.COLD


def _is_incoherent(data: ScoringInput) -> bool:
    """Smallest budget band paired with an industrial content volume."""
    return (
        data.monthly_marketing_budget is MarketingBudget.UNDER_2K
        and data.content_volume.min_videos >= INCOHERENT_VOLUME_THRESHOLD
    )


def score_lead(data: ScoringInput) -> ScoreResult:
    """Score a lead from 0 to 100 and explain every point of it."""
    components: list[ScoreComponent] = [
        ScoreComponent(
            dimension="budget",
            input_value=data.monthly_marketing_budget.value,
            points=BUDGET_POINTS[data.monthly_marketing_budget],
            reason="Monthly marketing budget - the strongest predictor of fit.",
        ),
        ScoreComponent(
            dimension="content_volume",
            input_value=data.content_volume.value,
            points=VOLUME_POINTS[data.content_volume],
            reason="Volume of content required per month.",
        ),
        ScoreComponent(
            dimension="timeline",
            input_value=data.start_timeline.value,
            points=TIMELINE_POINTS[data.start_timeline],
            reason="How soon they intend to start - a proxy for intent.",
        ),
        ScoreComponent(
            dimension="primary_goal",
            input_value=data.primary_goal.value,
            points=GOAL_POINTS[data.primary_goal],
            reason="Revenue-linked goals outrank awareness goals.",
        ),
        ScoreComponent(
            dimension="industry",
            input_value=data.industry.value,
            points=INDUSTRY_POINTS[data.industry],
            reason="How well Fluxframe's playbook performs in this vertical.",
        ),
    ]

    if _is_incoherent(data):
        components.append(
            ScoreComponent(
                dimension="coherence_penalty",
                input_value=(
                    f"{data.monthly_marketing_budget.value} + {data.content_volume.value}"
                ),
                points=INCOHERENT_BUDGET_VOLUME_PENALTY,
                reason=(
                    "Budget cannot support the requested content volume; "
                    "expectations are misaligned."
                ),
            )
        )

    raw_total = sum(component.points for component in components)
    score = max(MIN_SCORE, min(MAX_SCORE, raw_total))

    return ScoreResult(
        score=score,
        temperature=classify(score),
        version=SCORING_VERSION,
        components=tuple(components),
        raw_total=raw_total,
    )
