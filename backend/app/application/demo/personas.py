"""Synthetic lead personas for the demo generator.

The hard part of fake data is not generating it — it is generating data that is
*coherent*. A lead with a 10k budget, 30 videos a month, wanting to start
immediately, who is also "just researching" tells you nothing, and a dashboard
full of that looks obviously fake.

So this module does not sample fields independently. It picks a target
temperature first, then draws each answer from a pool weighted for that
temperature, then verifies the deterministic scorer actually agrees. A HOT
persona reads like a real hot lead because every answer points the same way.

Everything is driven by `random.Random(seed)`, so a seeded run is byte-for-byte
reproducible — which is what makes the distribution test in
tests/unit/application/test_demo_personas.py possible.

Safety rule, non-negotiable: every generated email is @example.com (RFC 2606,
reserved forever, cannot route). Generating plausible Gmail addresses would mean
writing real people's addresses into a CRM.
"""

import random
from dataclasses import dataclass

from app.application.dto.demo import DemoQuality, DemoScenario
from app.domain.leads.enums import (
    ContentVolume,
    Industry,
    LeadTemperature,
    MarketingBudget,
    MonthlyRevenue,
    PrimaryGoal,
    StartTimeline,
)
from app.domain.leads.scoring import ScoringInput, classify, score_lead

# --- Target distributions ----------------------------------------------------

#: The realistic baseline: most leads are warm, few are hot.
_QUALITY_WEIGHTS: dict[DemoQuality, dict[LeadTemperature, float]] = {
    DemoQuality.RANDOM: {
        LeadTemperature.HOT: 0.20,
        LeadTemperature.WARM: 0.45,
        LeadTemperature.COLD: 0.35,
    },
    DemoQuality.MOSTLY_HOT: {
        LeadTemperature.HOT: 0.65,
        LeadTemperature.WARM: 0.28,
        LeadTemperature.COLD: 0.07,
    },
    DemoQuality.MOSTLY_WARM: {
        LeadTemperature.HOT: 0.12,
        LeadTemperature.WARM: 0.70,
        LeadTemperature.COLD: 0.18,
    },
    DemoQuality.MOSTLY_COLD: {
        LeadTemperature.HOT: 0.04,
        LeadTemperature.WARM: 0.26,
        LeadTemperature.COLD: 0.70,
    },
}

#: A scenario is just a preset quality plus a campaign story for the UTMs.
_SCENARIO_QUALITY: dict[DemoScenario, DemoQuality] = {
    DemoScenario.NORMAL_WEEK: DemoQuality.RANDOM,
    DemoScenario.HIGH_INTENT_CAMPAIGN: DemoQuality.MOSTLY_HOT,
    DemoScenario.LOW_QUALITY_CAMPAIGN: DemoQuality.MOSTLY_COLD,
    DemoScenario.LEAD_SURGE: DemoQuality.RANDOM,
}

_INDUSTRY_WEIGHTS: dict[Industry, float] = {
    Industry.DENTAL: 0.20,
    Industry.REAL_ESTATE: 0.20,
    Industry.FITNESS: 0.15,
    Industry.BEAUTY: 0.15,
    Industry.LEGAL: 0.10,
    Industry.RESTAURANT: 0.10,
    Industry.PHYSIOTHERAPY: 0.10,
}

# --- Per-temperature answer pools -------------------------------------------
#
# The coherence trick: each temperature draws from its own weighted pools, so a
# HOT persona gets a real budget AND real urgency AND a revenue goal, rather
# than one strong signal and two weak ones.

_BUDGETS: dict[LeadTemperature, dict[MarketingBudget, float]] = {
    LeadTemperature.HOT: {
        MarketingBudget.OVER_10K: 0.55,
        MarketingBudget.FROM_5K_TO_10K: 0.45,
    },
    LeadTemperature.WARM: {
        MarketingBudget.FROM_5K_TO_10K: 0.35,
        MarketingBudget.FROM_2K_TO_5K: 0.55,
        MarketingBudget.OVER_10K: 0.10,
    },
    LeadTemperature.COLD: {
        MarketingBudget.UNDER_2K: 0.70,
        MarketingBudget.FROM_2K_TO_5K: 0.30,
    },
}

_VOLUMES: dict[LeadTemperature, dict[ContentVolume, float]] = {
    LeadTemperature.HOT: {
        ContentVolume.THIRTY_PLUS: 0.40,
        ContentVolume.TWENTY: 0.40,
        ContentVolume.TWELVE: 0.20,
    },
    LeadTemperature.WARM: {
        ContentVolume.TWELVE: 0.45,
        ContentVolume.EIGHT: 0.35,
        ContentVolume.TWENTY: 0.20,
    },
    LeadTemperature.COLD: {
        ContentVolume.FOUR: 0.50,
        ContentVolume.EIGHT: 0.35,
        # The incoherent case, on purpose: a tiny budget asking for 20+ videos.
        # It exists so the -10 coherence penalty is visible in demo data.
        ContentVolume.TWENTY: 0.15,
    },
}

_TIMELINES: dict[LeadTemperature, dict[StartTimeline, float]] = {
    LeadTemperature.HOT: {
        StartTimeline.IMMEDIATELY: 0.60,
        StartTimeline.WITHIN_30_DAYS: 0.40,
    },
    LeadTemperature.WARM: {
        StartTimeline.WITHIN_30_DAYS: 0.45,
        StartTimeline.ONE_TO_THREE_MONTHS: 0.45,
        StartTimeline.IMMEDIATELY: 0.10,
    },
    LeadTemperature.COLD: {
        StartTimeline.RESEARCHING: 0.55,
        StartTimeline.ONE_TO_THREE_MONTHS: 0.45,
    },
}

_GOALS: dict[LeadTemperature, dict[PrimaryGoal, float]] = {
    LeadTemperature.HOT: {
        PrimaryGoal.LEAD_GENERATION: 0.45,
        PrimaryGoal.SALES: 0.40,
        PrimaryGoal.PRODUCT_LAUNCH: 0.15,
    },
    LeadTemperature.WARM: {
        PrimaryGoal.LEAD_GENERATION: 0.35,
        PrimaryGoal.SALES: 0.25,
        PrimaryGoal.BRAND_AWARENESS: 0.25,
        PrimaryGoal.SOCIAL_GROWTH: 0.15,
    },
    LeadTemperature.COLD: {
        PrimaryGoal.SOCIAL_GROWTH: 0.40,
        PrimaryGoal.BRAND_AWARENESS: 0.40,
        PrimaryGoal.LEAD_GENERATION: 0.20,
    },
}

_REVENUES: dict[LeadTemperature, dict[MonthlyRevenue, float]] = {
    LeadTemperature.HOT: {
        MonthlyRevenue.OVER_500K: 0.30,
        MonthlyRevenue.FROM_100K_TO_500K: 0.50,
        MonthlyRevenue.FROM_50K_TO_100K: 0.20,
    },
    LeadTemperature.WARM: {
        MonthlyRevenue.FROM_100K_TO_500K: 0.30,
        MonthlyRevenue.FROM_50K_TO_100K: 0.50,
        MonthlyRevenue.UNDER_50K: 0.20,
    },
    LeadTemperature.COLD: {
        MonthlyRevenue.UNDER_50K: 0.70,
        MonthlyRevenue.FROM_50K_TO_100K: 0.30,
    },
}

# --- Name and company vocabulary --------------------------------------------

_FIRST_NAMES = (
    "Sarah",
    "James",
    "Priya",
    "Daniel",
    "Aisha",
    "Michael",
    "Elena",
    "Omar",
    "Chloe",
    "Marcus",
    "Nadia",
    "Thomas",
    "Grace",
    "Liam",
    "Fatima",
    "Ethan",
    "Zara",
    "Noah",
    "Isabelle",
    "Hassan",
    "Maya",
    "Oliver",
    "Amara",
    "Lucas",
)

_LAST_NAMES = (
    "Morgan",
    "Whitfield",
    "Sharma",
    "Okafor",
    "Bennett",
    "Larsen",
    "Nakamura",
    "Rivera",
    "Castellano",
    "Dube",
    "Kowalski",
    "Fitzgerald",
    "Haddad",
    "Lindqvist",
    "Petrov",
    "Osei",
    "Vance",
    "Moreau",
    "Ibrahim",
    "Delaney",
)

#: Company names are industry-specific, so a dental practice does not end up
#: called "Iron Forge Gym". Cheap detail, large credibility difference.
_COMPANY_PATTERNS: dict[Industry, tuple[tuple[str, ...], tuple[str, ...]]] = {
    Industry.DENTAL: (
        ("Bright", "Lumen", "Northgate", "Cedar", "Clearwater", "Meridian"),
        ("Dental Studio", "Dental Care", "Orthodontics", "Dental Practice"),
    ),
    Industry.FITNESS: (
        ("Iron", "Pulse", "Summit", "Forge", "Kinetic", "Apex"),
        ("Strength Co", "Fitness", "Performance", "Athletic Club"),
    ),
    Industry.REAL_ESTATE: (
        ("Harbour", "Kingsley", "Stonebridge", "Ashford", "Vantage", "Belmont"),
        ("Property Group", "Estates", "Realty", "Property Partners"),
    ),
    Industry.BEAUTY: (
        ("Bloom", "Lustre", "Velvet", "Aurora", "Petal", "Glow"),
        ("Skin Clinic", "Aesthetics", "Beauty Lounge", "Skin Studio"),
    ),
    Industry.LEGAL: (
        ("Harrow", "Blackwell", "Ashton", "Pemberton", "Calder", "Thornbury"),
        ("Legal", "Solicitors", "Law Partners", "Legal Group"),
    ),
    Industry.PHYSIOTHERAPY: (
        ("Motion", "Align", "Restore", "Pivot", "Core", "Kinetix"),
        ("Physiotherapy", "Physio Clinic", "Sports Therapy", "Rehab Clinic"),
    ),
    Industry.RESTAURANT: (
        ("Saffron", "Olive", "Copper", "Harvest", "Ember", "Larder"),
        ("Kitchen", "Dining", "Restaurant Group", "Bistro"),
    ),
    Industry.ECOMMERCE: (
        ("North", "Loop", "Field", "Standard", "Wren"),
        ("Supply Co", "Goods", "Collective", "Commerce"),
    ),
    Industry.SAAS: (
        ("Cobalt", "Nimbus", "Ledger", "Beacon", "Signal"),
        ("Software", "Labs", "Systems", "Platform"),
    ),
    Industry.OTHER: (
        ("Anchor", "Bridge", "Union", "Compass"),
        ("Group", "Partners", "Company"),
    ),
}

#: Free-text messages, written in the voice of each temperature band. These are
#: what the Phase 6 AI brief actually reads, so they carry real signal: a hot
#: message names a deadline and a number, a cold one asks about price.
_MESSAGES: dict[LeadTemperature, tuple[str, ...]] = {
    LeadTemperature.HOT: (
        "We have a new location opening in six weeks and no content plan. "
        "Our current agency has not delivered in two months and we need to move now.",
        "We are spending on ads already but the creative is stale and CPL has "
        "doubled since January. We need someone who can produce volume fast.",
        "Board has signed off the budget for this quarter. We need a partner who "
        "can start within the next fortnight and own the whole channel.",
        "We tried an in-house hire and it did not work. Looking to outsource "
        "properly this time and we want to see a pipeline impact by Q3.",
    ),
    LeadTemperature.WARM: (
        "We post occasionally but there is no real strategy behind it. Keen to "
        "understand what a consistent approach would look like and what it costs.",
        "Our competitors are all over short-form and we are not. Want to explore "
        "what is realistic for a business our size.",
        "We get decent engagement but it does not turn into enquiries. Trying to "
        "work out whether that is a content problem or a targeting problem.",
        "Planning next year's marketing now. Would like to understand your "
        "process before we commit to anything.",
    ),
    LeadTemperature.COLD: (
        "Just having a look around at the moment. Can you send over pricing?",
        "Not sure we have the budget yet but wanted to see what is involved.",
        "We are a small team and mostly do our own social. Curious what an agency "
        "would actually add.",
        "Doing some early research for a possible rebrand later in the year.",
    ),
}

# --- Attribution stories -----------------------------------------------------

_SCENARIO_ATTRIBUTION: dict[DemoScenario, tuple[str, str, str]] = {
    DemoScenario.NORMAL_WEEK: ("google", "organic", "brand_search"),
    DemoScenario.HIGH_INTENT_CAMPAIGN: ("linkedin", "cpc", "q3_agency_offer"),
    DemoScenario.LOW_QUALITY_CAMPAIGN: ("facebook", "cpc", "broad_awareness"),
    DemoScenario.LEAD_SURGE: ("instagram", "social", "founder_video_viral"),
}


@dataclass(frozen=True, slots=True)
class DemoPersona:
    """A complete, coherent synthetic lead."""

    first_name: str
    last_name: str
    email: str
    company_name: str
    website: str
    phone: str
    industry: Industry
    monthly_revenue: MonthlyRevenue
    monthly_marketing_budget: MarketingBudget
    content_volume: ContentVolume
    primary_goal: PrimaryGoal
    start_timeline: StartTimeline
    message: str
    utm_source: str
    utm_medium: str
    utm_campaign: str
    #: The band we aimed for. The real score is computed by the real scorer when
    #: the lead is captured — this is only the generator's intent.
    intended_temperature: LeadTemperature


def _weighted_choice[T](rng: random.Random, weights: dict[T, float]) -> T:
    """Pick one key, proportional to its weight."""
    options = list(weights.keys())
    return rng.choices(options, weights=[weights[o] for o in options], k=1)[0]


def _slugify(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")


#: How many times to resample before accepting a persona that missed its band.
#: The pools are tuned well enough that this almost never exhausts; the cap
#: exists so the generator cannot loop forever if someone edits the weights.
_MAX_COHERENCE_ATTEMPTS = 12


def build_persona(
    rng: random.Random,
    *,
    quality: DemoQuality,
    scenario: DemoScenario,
    industry: Industry | None,
    sequence: int,
) -> DemoPersona:
    """Generate one coherent persona.

    `sequence` makes the email address unique within a batch.
    """
    effective_quality = _SCENARIO_QUALITY[scenario] if quality is DemoQuality.RANDOM else quality
    target = _weighted_choice(rng, _QUALITY_WEIGHTS[effective_quality])
    chosen_industry = industry or _weighted_choice(rng, _INDUSTRY_WEIGHTS)

    budget = _weighted_choice(rng, _BUDGETS[target])
    volume = _weighted_choice(rng, _VOLUMES[target])
    timeline = _weighted_choice(rng, _TIMELINES[target])
    goal = _weighted_choice(rng, _GOALS[target])

    # Resample until the real scorer agrees with the band we aimed for. This is
    # the step that keeps generated data honest: the generator does not get to
    # assert a temperature, it has to earn one from the same rules the
    # production path uses.
    for _ in range(_MAX_COHERENCE_ATTEMPTS):
        result = score_lead(
            ScoringInput(
                monthly_marketing_budget=budget,
                content_volume=volume,
                start_timeline=timeline,
                primary_goal=goal,
                industry=chosen_industry,
            )
        )
        if classify(result.score) is target:
            break
        budget = _weighted_choice(rng, _BUDGETS[target])
        volume = _weighted_choice(rng, _VOLUMES[target])
        timeline = _weighted_choice(rng, _TIMELINES[target])
        goal = _weighted_choice(rng, _GOALS[target])

    first = rng.choice(_FIRST_NAMES)
    last = rng.choice(_LAST_NAMES)
    prefix, suffix = _COMPANY_PATTERNS[chosen_industry]
    company = f"{rng.choice(prefix)} {rng.choice(suffix)}"
    company_slug = _slugify(company)

    source, medium, campaign = _SCENARIO_ATTRIBUTION[scenario]

    return DemoPersona(
        first_name=first,
        last_name=last,
        # RFC 2606 reserved domain. Never routable, never someone's real inbox.
        email=f"{first.lower()}.{last.lower()}.demo{sequence:03d}@example.com",
        company_name=company,
        website=f"https://www.{company_slug}.example.com",
        phone=f"+44 7700 {rng.randint(100000, 999999)}",
        industry=chosen_industry,
        monthly_revenue=_weighted_choice(rng, _REVENUES[target]),
        monthly_marketing_budget=budget,
        content_volume=volume,
        primary_goal=goal,
        start_timeline=timeline,
        message=rng.choice(_MESSAGES[target]),
        utm_source=source,
        utm_medium=medium,
        utm_campaign=campaign,
        intended_temperature=target,
    )
