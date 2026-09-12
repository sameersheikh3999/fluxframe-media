"""Tests for the AI sales-brief adapter.

No API key, no network, no spend — `respx` intercepts httpx and returns canned
Anthropic responses. What is being tested is the part that actually matters in
an LLM integration: what happens when the model returns something unusable.

The rule this file enforces: the adapter either produces a fully valid
`SalesBrief` or raises. It never lets a half-built object, an invented enum
value or an empty list reach the application layer — because a salesperson would
act on it.
"""

from dataclasses import replace
from typing import Any

import httpx
import pytest
import respx

from app.application.errors import AiResponseError, AiUnavailableError
from app.application.ports.sales_brief_generator import SalesBriefRequest
from app.infrastructure.ai.anthropic_client import (
    ANTHROPIC_BASE_URL,
    MESSAGES_PATH,
    AnthropicSalesBriefGenerator,
    NullSalesBriefGenerator,
)
from app.infrastructure.ai.prompts import PROMPT_VERSION

pytestmark = pytest.mark.unit

MESSAGES_URL = f"{ANTHROPIC_BASE_URL}{MESSAGES_PATH}"

VALID_BRIEF = {
    "summary": "A growing clinic opening a second site with no content plan.",
    "pain_points": ["No content plan", "New location in six weeks"],
    "urgency": "high",
    "suggested_service": "short_form_video",
    "opening_line": "I hear the second clinic opens in six weeks.",
    "confidence": "high",
}


def request() -> SalesBriefRequest:
    return SalesBriefRequest(
        company_name="Bloom Skin Clinic",
        industry="beauty",
        monthly_revenue="100k_500k",
        marketing_budget="10k_plus",
        content_volume="30_plus",
        primary_goal="lead_generation",
        start_timeline="immediately",
        message="New clinic opening in six weeks and no content plan.",
        deterministic_score=100,
        deterministic_temperature="hot",
    )


def anthropic_response(
    tool_input: dict[str, Any] | None = None,
    *,
    content: list[dict[str, Any]] | None = None,
) -> httpx.Response:
    blocks = content
    if blocks is None:
        blocks = [
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "submit_sales_brief",
                "input": tool_input if tool_input is not None else VALID_BRIEF,
            }
        ]
    return httpx.Response(
        200,
        json={
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "content": blocks,
            "usage": {"input_tokens": 820, "output_tokens": 145},
        },
    )


async def generate_with(response: httpx.Response) -> Any:
    async with httpx.AsyncClient() as http:
        generator = AnthropicSalesBriefGenerator(api_key="key", http_client=http)
        with respx.mock:
            respx.post(MESSAGES_URL).mock(return_value=response)
            return await generator.generate(request())


async def expect_failure(response: httpx.Response, error: type[Exception]) -> None:
    async with httpx.AsyncClient() as http:
        generator = AnthropicSalesBriefGenerator(api_key="key", http_client=http)
        with respx.mock:
            respx.post(MESSAGES_URL).mock(return_value=response)
            with pytest.raises(error):
                await generator.generate(request())


# --- the happy path ---------------------------------------------------------


async def test_a_valid_response_becomes_a_structured_brief() -> None:
    brief = await generate_with(anthropic_response())

    assert brief.summary.startswith("A growing clinic")
    assert brief.pain_points == ("No content plan", "New location in six weeks")
    assert brief.urgency == "high"
    assert brief.suggested_service == "short_form_video"
    assert brief.confidence == "high"


async def test_token_usage_and_latency_are_captured() -> None:
    """An AI feature you cannot measure is one you cannot improve or budget."""
    brief = await generate_with(anthropic_response())

    assert brief.input_tokens == 820
    assert brief.output_tokens == 145
    assert brief.latency_ms >= 0
    assert brief.prompt_version == PROMPT_VERSION


async def test_the_request_forces_the_structured_tool_call() -> None:
    """Without tool_choice the model may answer in prose, and we would be back
    to parsing free text."""
    async with httpx.AsyncClient() as http:
        generator = AnthropicSalesBriefGenerator(api_key="key", http_client=http)
        with respx.mock:
            route = respx.post(MESSAGES_URL).mock(return_value=anthropic_response())
            await generator.generate(request())

    body = route.calls[0].request.content.decode()
    assert "submit_sales_brief" in body
    assert "tool_choice" in body
    # The deterministic score is given as context so the narrative agrees with
    # the number a salesperson can already see.
    assert "100/100" in body


async def test_the_api_key_goes_in_the_header_not_the_body() -> None:
    async with httpx.AsyncClient() as http:
        generator = AnthropicSalesBriefGenerator(api_key="sk-secret", http_client=http)
        with respx.mock:
            route = respx.post(MESSAGES_URL).mock(return_value=anthropic_response())
            await generator.generate(request())

    call = route.calls[0].request
    assert call.headers["x-api-key"] == "sk-secret"
    assert "sk-secret" not in call.content.decode()


async def test_a_lead_with_no_message_still_produces_a_brief() -> None:
    """The prompt substitutes a placeholder telling the model to lower its own
    confidence rather than inventing detail."""
    async with httpx.AsyncClient() as http:
        generator = AnthropicSalesBriefGenerator(api_key="key", http_client=http)
        with respx.mock:
            route = respx.post(MESSAGES_URL).mock(return_value=anthropic_response())
            # `replace` rather than **__dict__: SalesBriefRequest uses
            # slots=True, so it has no instance dictionary.
            await generator.generate(replace(request(), message=None))

    assert "did not leave a message" in route.calls[0].request.content.decode()


# --- bad model output -------------------------------------------------------


async def test_prose_instead_of_a_tool_call_is_rejected() -> None:
    await expect_failure(
        anthropic_response(content=[{"type": "text", "text": "Here you go!"}]),
        AiResponseError,
    )


@pytest.mark.parametrize("field", ["summary", "opening_line"])
async def test_a_missing_required_string_is_rejected(field: str) -> None:
    payload = {**VALID_BRIEF}
    del payload[field]
    await expect_failure(anthropic_response(payload), AiResponseError)


async def test_an_empty_string_field_is_rejected() -> None:
    await expect_failure(anthropic_response({**VALID_BRIEF, "summary": "   "}), AiResponseError)


async def test_an_empty_pain_point_list_is_rejected() -> None:
    await expect_failure(anthropic_response({**VALID_BRIEF, "pain_points": []}), AiResponseError)


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("urgency", "extremely_high"),
        ("confidence", "certain"),
        ("suggested_service", "seo_consulting"),
    ],
)
async def test_an_invented_enum_value_is_rejected(field: str, bad_value: str) -> None:
    """The tool schema constrains the model; this constrains reality.

    Never trust a shape you did not verify yourself — both checks are cheap.
    """
    await expect_failure(anthropic_response({**VALID_BRIEF, field: bad_value}), AiResponseError)


async def test_too_many_pain_points_are_truncated_not_rejected() -> None:
    """Over-delivery is a formatting problem, not a correctness one."""
    brief = await generate_with(
        anthropic_response({**VALID_BRIEF, "pain_points": [f"p{i}" for i in range(9)]})
    )
    assert len(brief.pain_points) == 4


# --- provider failures ------------------------------------------------------


@pytest.mark.parametrize("status_code", [401, 429, 500, 529])
async def test_provider_errors_surface_as_unavailable(status_code: int) -> None:
    await expect_failure(httpx.Response(status_code, json={}), AiUnavailableError)


async def test_a_timeout_surfaces_as_unavailable() -> None:
    async with httpx.AsyncClient() as http:
        generator = AnthropicSalesBriefGenerator(api_key="key", http_client=http)
        with respx.mock:
            respx.post(MESSAGES_URL).mock(side_effect=httpx.ReadTimeout("slow"))
            with pytest.raises(AiUnavailableError):
                await generator.generate(request())


async def test_no_api_key_means_unavailable_not_fabricated() -> None:
    async with httpx.AsyncClient() as http:
        generator = AnthropicSalesBriefGenerator(api_key=None, http_client=http)
        assert generator.is_configured is False
        with pytest.raises(AiUnavailableError):
            await generator.generate(request())


async def test_the_null_generator_refuses_clearly() -> None:
    """It does not invent a plausible brief. A fabricated brief would be worse
    than none, because a salesperson would act on it."""
    generator = NullSalesBriefGenerator()
    assert generator.is_configured is False
    with pytest.raises(AiUnavailableError) as info:
        await generator.generate(request())
    assert "ANTHROPIC_API_KEY" in str(info.value)


# --- cost estimation --------------------------------------------------------


def test_cost_is_estimated_from_token_counts() -> None:
    generator = AnthropicSalesBriefGenerator(api_key="k", http_client=httpx.AsyncClient())
    cost = generator.estimate_cost_usd(input_tokens=1_000_000, output_tokens=0)
    assert cost == pytest.approx(3.00)


def test_cost_is_none_when_usage_is_unknown() -> None:
    generator = AnthropicSalesBriefGenerator(api_key="k", http_client=httpx.AsyncClient())
    assert generator.estimate_cost_usd(None, None) is None
