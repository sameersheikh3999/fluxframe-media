"""Port: AI observability.

Every LLM call is recorded — successes and failures alike — because an AI
feature you cannot measure is an AI feature you cannot improve. Six months from
now the questions that matter are:

    Which prompt version produced the briefs sales actually liked?
    What is this feature costing per month?
    How often does the model return something we cannot parse?
    Did latency regress when we changed models?

None of those are answerable from application logs alone, and all of them are
answerable from one table. That is why AI observability is a port with its own
storage rather than a `logger.info` call.

`human_rating` is deliberately present and deliberately unused for now: it is
the hook for a thumbs-up/down control on the dashboard, which is what turns a
pile of runs into an evaluation set.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AiRunRecord:
    """One call to a language model."""

    feature: str
    provider: str
    model: str
    prompt_version: str
    status: str
    created_at: datetime

    lead_id: UUID | None = None
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    #: Estimated in the adapter from token counts and a published price table.
    #: Approximate by nature — good enough to spot a cost regression.
    estimated_cost_usd: float | None = None
    correlation_id: str | None = None
    error: str | None = None
    output: dict[str, object] = field(default_factory=dict)


class AiRunRecorder(Protocol):
    """Persists AI run records."""

    async def record(self, run: AiRunRecord) -> None:
        """Store one run.

        Must never raise into the caller: failing to record telemetry is not a
        reason to fail the user's request. Implementations log and swallow.
        """
        ...
