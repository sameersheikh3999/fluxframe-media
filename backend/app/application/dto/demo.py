"""Controlled vocabularies for the demo generator.

These live in `dto/` rather than in `demo/personas.py` because they are part of
the use case's input contract, and the transport layer needs them too: they are
the values a request body may carry, and the options the /demo page renders.

Keeping them here means the enum values have exactly one definition shared by
the API schema, the service and the persona builder — the same argument that
lets `app/schemas/leads.py` import the domain enums. A vocabulary duplicated
across layers drifts; a vocabulary defined once cannot.
"""

from enum import StrEnum


class DemoQuality(StrEnum):
    """How the operator wants a generated batch skewed."""

    RANDOM = "random"
    MOSTLY_COLD = "mostly_cold"
    MOSTLY_WARM = "mostly_warm"
    MOSTLY_HOT = "mostly_hot"


class DemoScenario(StrEnum):
    """A narrative shortcut that sets quality and attribution together."""

    NORMAL_WEEK = "normal_week"
    HIGH_INTENT_CAMPAIGN = "high_intent_campaign"
    LOW_QUALITY_CAMPAIGN = "low_quality_campaign"
    LEAD_SURGE = "lead_surge"
