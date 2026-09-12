"""Port: turning a lead's free text into a structured sales brief.

This is the AI boundary, and the shape of it is the important part.

`SalesBrief` is a *structured* result — fields, not prose. The application layer
never receives a blob of model output and never parses one; the adapter is
responsible for getting structure out of the model and validating it before it
crosses this line. If the model returns something unusable, the adapter raises,
and the caller degrades gracefully.

What this port deliberately does NOT do: score the lead. Scoring is a
deterministic business rule (app/domain/leads/scoring.py) and must stay
explainable and stable. The LLM interprets the one thing rules cannot — the
prospect's own words — and nothing else.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SalesBriefRequest:
    """The context the generator is allowed to see.

    Explicitly enumerated rather than passing the whole Lead: the model has no
    business seeing an idempotency key, a CRM id or internal sync errors.
    """

    company_name: str
    industry: str
    monthly_revenue: str
    marketing_budget: str
    content_volume: str
    primary_goal: str
    start_timeline: str
    message: str | None
    deterministic_score: int
    deterministic_temperature: str


@dataclass(frozen=True, slots=True)
class SalesBrief:
    """A validated, structured brief. Never raw model text."""

    summary: str
    pain_points: tuple[str, ...]
    urgency: str
    suggested_service: str
    opening_line: str
    confidence: str
    model: str
    #: Version of the prompt that produced this, so a change in output quality
    #: can be traced to a change in the prompt rather than guessed at.
    prompt_version: str
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None


class SalesBriefGenerator(Protocol):
    """Generates a structured sales brief from a lead's own words."""

    async def generate(self, request: SalesBriefRequest) -> SalesBrief:
        """Produce a brief.

        Raises AiUnavailableError if the provider cannot be reached or is not
        configured, and AiResponseError if the model returned something that
        does not satisfy the expected structure.
        """
        ...

    @property
    def is_configured(self) -> bool:
        """False when no API key is present. AI is strictly optional."""
        ...
