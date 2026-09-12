"""The Anthropic adapter. Satisfies ports.sales_brief_generator.SalesBriefGenerator.

Everything model-specific is contained here: the API shape, the model name, the
token accounting, the cost estimate, the validation of what came back. The layer
above receives a typed `SalesBrief` or an exception, and has no idea which
provider produced it.

Three things this adapter does that a naive LLM call does not:

**Structured output via tool use.** The model is given a tool with a JSON Schema
and told to call it. That is materially more reliable than asking for JSON in
prose and parsing the result, because the API itself constrains the shape.

**Validation anyway.** Even with a schema, we check every field before building
the DTO. An enum the model invented, a missing key, an empty list — all raise
`AiResponseError` rather than propagating a half-built object. Never trust a
shape you did not verify yourself.

**Measurement.** Latency and token counts come back on every call and are
recorded in `ai_runs`. A feature you cannot measure is a feature you cannot
improve or budget for.

Written directly against the HTTP API with httpx rather than the SDK: it is one
endpoint, we already depend on httpx for HubSpot, and it keeps exactly what is
sent to the model visible in this file.
"""

import time
from typing import Any

import httpx

from app.application.errors import AiResponseError, AiUnavailableError
from app.application.ports.sales_brief_generator import (
    SalesBrief,
    SalesBriefRequest,
)
from app.infrastructure.ai.prompts import (
    NO_MESSAGE_PLACEHOLDER,
    PROMPT_VERSION,
    SALES_BRIEF_TOOL,
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)
from app.observability.logging import get_logger

_logger = get_logger(__name__)

ANTHROPIC_BASE_URL = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"
MESSAGES_PATH = "/v1/messages"

#: Published per-million-token prices, used only for a rough cost estimate on
#: the ai_runs row. Approximate by design — good enough to notice a regression,
#: not an invoice.
_PRICE_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-sonnet-5": (3.00, 15.00),
    "claude-opus-5": (15.00, 75.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
}
_DEFAULT_PRICE = (3.00, 15.00)

_VALID_URGENCY = frozenset({"high", "medium", "low"})
_VALID_CONFIDENCE = frozenset({"high", "medium", "low"})
_VALID_SERVICES = frozenset(
    {
        "short_form_video",
        "social_media_management",
        "content_strategy",
        "paid_social",
        "creator_campaigns",
    }
)


class AnthropicSalesBriefGenerator:
    """Generates sales briefs with Claude."""

    def __init__(
        self,
        *,
        api_key: str | None,
        http_client: httpx.AsyncClient,
        model: str = "claude-sonnet-5",
        max_tokens: int = 1024,
        base_url: str = ANTHROPIC_BASE_URL,
    ) -> None:
        self._api_key = api_key
        self._http = http_client
        self._model = model
        self._max_tokens = max_tokens
        self._base_url = base_url.rstrip("/")

    @property
    def is_configured(self) -> bool:
        """AI is strictly optional. Without a key the rest of the app is intact."""
        return bool(self._api_key)

    async def generate(self, request: SalesBriefRequest) -> SalesBrief:
        if not self._api_key:
            raise AiUnavailableError("ANTHROPIC_API_KEY is not set; AI sales briefs are disabled.")

        body = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "system": SYSTEM_PROMPT,
            "tools": [SALES_BRIEF_TOOL],
            # Force the tool call. Without this the model may reply in prose and
            # we would be back to parsing free text.
            "tool_choice": {"type": "tool", "name": SALES_BRIEF_TOOL["name"]},
            "messages": [{"role": "user", "content": _render_user_prompt(request)}],
        }

        started = time.perf_counter()
        try:
            response = await self._http.post(
                f"{self._base_url}{MESSAGES_PATH}",
                json=body,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
            )
        except httpx.TimeoutException as exc:
            raise AiUnavailableError(f"The AI provider timed out: {exc}") from exc
        except httpx.TransportError as exc:
            raise AiUnavailableError(f"Could not reach the AI provider: {exc}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)

        if response.status_code == 401:
            raise AiUnavailableError("The AI provider rejected the API key.")
        if response.status_code == 429:
            raise AiUnavailableError("The AI provider is rate limiting requests.")
        if not response.is_success:
            raise AiUnavailableError(f"The AI provider returned {response.status_code}.")

        payload = response.json()
        brief_input = _extract_tool_input(payload)
        usage = payload.get("usage") or {}
        input_tokens = _as_int(usage.get("input_tokens"))
        output_tokens = _as_int(usage.get("output_tokens"))

        _logger.info(
            "ai_sales_brief_generated",
            model=self._model,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        return _build_brief(
            brief_input,
            model=self._model,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def estimate_cost_usd(
        self, input_tokens: int | None, output_tokens: int | None
    ) -> float | None:
        """Rough spend for one call, for the ai_runs row."""
        if input_tokens is None and output_tokens is None:
            return None
        price_in, price_out = _PRICE_PER_MTOK.get(self._model, _DEFAULT_PRICE)
        return round(
            (input_tokens or 0) / 1_000_000 * price_in
            + (output_tokens or 0) / 1_000_000 * price_out,
            6,
        )


class NullSalesBriefGenerator:
    """Used when no AI key is configured.

    Not a stub that fabricates output — it refuses, clearly. Inventing a
    plausible-looking brief would be worse than having none, because a
    salesperson would act on it.
    """

    @property
    def is_configured(self) -> bool:
        return False

    async def generate(self, request: SalesBriefRequest) -> SalesBrief:
        raise AiUnavailableError(
            "No AI provider is configured. Set ANTHROPIC_API_KEY to enable sales briefs."
        )


def _render_user_prompt(request: SalesBriefRequest) -> str:
    return USER_PROMPT_TEMPLATE.format(
        company_name=request.company_name,
        industry=request.industry,
        monthly_revenue=request.monthly_revenue,
        marketing_budget=request.marketing_budget,
        content_volume=request.content_volume,
        primary_goal=request.primary_goal,
        start_timeline=request.start_timeline,
        deterministic_score=request.deterministic_score,
        deterministic_temperature=request.deterministic_temperature,
        message=(request.message or NO_MESSAGE_PLACEHOLDER).strip(),
    )


def _extract_tool_input(payload: dict[str, Any]) -> dict[str, Any]:
    """Find the tool_use block in the response.

    A model that replied in prose despite `tool_choice` is a contract violation,
    not something to paper over with a regex.
    """
    for block in payload.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            tool_input = block.get("input")
            if isinstance(tool_input, dict):
                return tool_input
    raise AiResponseError("The model did not return a structured sales brief.")


def _build_brief(
    data: dict[str, Any],
    *,
    model: str,
    latency_ms: int,
    input_tokens: int | None,
    output_tokens: int | None,
) -> SalesBrief:
    """Validate the model's output, then build the DTO.

    The schema constrains the model; this constrains reality. Both are cheap.
    """
    summary = _require_text(data, "summary")
    opening_line = _require_text(data, "opening_line")

    raw_points = data.get("pain_points")
    if not isinstance(raw_points, list) or not raw_points:
        raise AiResponseError("The model returned no pain points.")
    pain_points = tuple(str(p).strip() for p in raw_points if str(p).strip())[:4]
    if not pain_points:
        raise AiResponseError("The model returned only empty pain points.")

    urgency = _require_enum(data, "urgency", _VALID_URGENCY)
    confidence = _require_enum(data, "confidence", _VALID_CONFIDENCE)
    suggested_service = _require_enum(data, "suggested_service", _VALID_SERVICES)

    return SalesBrief(
        summary=summary,
        pain_points=pain_points,
        urgency=urgency,
        suggested_service=suggested_service,
        opening_line=opening_line,
        confidence=confidence,
        model=model,
        prompt_version=PROMPT_VERSION,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _require_text(data: dict[str, Any], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise AiResponseError(f"The model returned no '{field}'.")
    return value.strip()


def _require_enum(data: dict[str, Any], field: str, allowed: frozenset[str]) -> str:
    value = data.get(field)
    if not isinstance(value, str) or value not in allowed:
        raise AiResponseError(f"The model returned an invalid '{field}': {value!r}.")
    return value


def _as_int(value: object) -> int | None:
    return int(value) if isinstance(value, int) else None
