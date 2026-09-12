"""The controlled vocabularies of the leads domain.

Every one of these is a `StrEnum`, so the member IS its wire value: the string
that arrives in JSON, the string stored in PostgreSQL, and the string the
frontend dropdown submits are all the same literal. One source of truth.

Two of them carry an ordinal (`min_videos`, `rank`). That is deliberate. The
scoring rules need to express "content volume of 20 or more", and expressing
that as a string comparison would be a bug waiting to happen. Putting the
ordering on the data means the rule reads as what it means.
"""

from enum import StrEnum


class MonthlyRevenue(StrEnum):
    """Self-reported business size. Captured for sales context.

    Deliberately NOT scored in v1: revenue tells a salesperson how big the
    opportunity is, but it does not predict intent, which is what the score is
    for. A large business that is 'just researching' is not a hot lead.
    """

    UNDER_50K = "under_50k"
    FROM_50K_TO_100K = "50k_100k"
    FROM_100K_TO_500K = "100k_500k"
    OVER_500K = "500k_plus"


class MarketingBudget(StrEnum):
    """Monthly marketing budget. The single strongest scoring signal."""

    UNDER_2K = "under_2k"
    FROM_2K_TO_5K = "2k_5k"
    FROM_5K_TO_10K = "5k_10k"
    OVER_10K = "10k_plus"

    @property
    def rank(self) -> int:
        """0 (smallest) to 3 (largest). Lets rules compare bands by size."""
        return _BUDGET_RANK[self]


_BUDGET_RANK: dict[MarketingBudget, int] = {
    MarketingBudget.UNDER_2K: 0,
    MarketingBudget.FROM_2K_TO_5K: 1,
    MarketingBudget.FROM_5K_TO_10K: 2,
    MarketingBudget.OVER_10K: 3,
}


class ContentVolume(StrEnum):
    """Videos wanted per month."""

    FOUR = "4"
    EIGHT = "8"
    TWELVE = "12"
    TWENTY = "20"
    THIRTY_PLUS = "30_plus"

    @property
    def min_videos(self) -> int:
        """The lower bound of the band, as a number.

        This is what makes the coherence rule readable:
            volume.min_videos >= 20
        instead of a string comparison that would rank "4" above "20".
        """
        return _VOLUME_MIN_VIDEOS[self]


_VOLUME_MIN_VIDEOS: dict[ContentVolume, int] = {
    ContentVolume.FOUR: 4,
    ContentVolume.EIGHT: 8,
    ContentVolume.TWELVE: 12,
    ContentVolume.TWENTY: 20,
    ContentVolume.THIRTY_PLUS: 30,
}


class PrimaryGoal(StrEnum):
    """What the prospect wants the content to achieve."""

    LEAD_GENERATION = "lead_generation"
    SALES = "sales"
    BRAND_AWARENESS = "brand_awareness"
    SOCIAL_GROWTH = "social_growth"
    PRODUCT_LAUNCH = "product_launch"


class StartTimeline(StrEnum):
    """How soon they want to begin. A proxy for intent."""

    IMMEDIATELY = "immediately"
    WITHIN_30_DAYS = "within_30_days"
    ONE_TO_THREE_MONTHS = "one_to_three_months"
    RESEARCHING = "researching"


class Industry(StrEnum):
    """Industries Fluxframe positions itself around.

    OTHER exists so the form never rejects a real prospect who does not fit the
    list. It scores neutrally rather than negatively.
    """

    DENTAL = "dental"
    FITNESS = "fitness"
    REAL_ESTATE = "real_estate"
    BEAUTY = "beauty"
    LEGAL = "legal"
    PHYSIOTHERAPY = "physiotherapy"
    RESTAURANT = "restaurant"
    ECOMMERCE = "ecommerce"
    SAAS = "saas"
    OTHER = "other"


class LeadTemperature(StrEnum):
    """The score, bucketed. A MODEL OUTPUT — it changes when scoring changes."""

    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


class LeadStatus(StrEnum):
    """Where the lead sits in the sales process.

    A PROCESS STATE — it changes when a human (or, later, an agent) acts.

    Deliberately independent of LeadTemperature. Conflating them would mean
    that re-scoring a lead rewrites sales history, and that a model change
    silently moves deals through the pipeline. Temperature advises; status
    records what actually happened.
    """

    NEW = "new"
    QUALIFIED = "qualified"
    CONTACTED = "contacted"
    BOOKED = "booked"
    WON = "won"
    LOST = "lost"
    DISQUALIFIED = "disqualified"


class LeadSource(StrEnum):
    """Where the lead came from."""

    WEBSITE = "website"
    DEMO_GENERATOR = "demo_generator"


class CrmSyncStatus(StrEnum):
    """State of this lead's synchronisation with HubSpot."""

    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"
    #: Demo leads when HUBSPOT_SYNC_DEMO_LEADS is off, or no token configured.
    SKIPPED = "skipped"
