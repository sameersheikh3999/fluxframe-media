"""Tests for the HubSpot adapter.

Every HubSpot failure mode is exercised here with `respx`, which intercepts
httpx at the transport layer. No network, no API key, no HubSpot account — and
yet the retry policy is genuinely verified, because the policy is entirely
determined by how responses are classified.

That classification is the highest-leverage code in the integration: it decides
whether a wrong token is noticed in minutes or hidden behind a queue that
quietly grows forever.
"""

import httpx
import pytest
import respx

from app.application.errors import (
    CrmNotConfiguredError,
    CrmPermanentError,
    CrmTransientError,
)
from app.application.ports.crm_client import CrmContactUpsert
from app.infrastructure.hubspot.client import (
    DEFAULT_BASE_URL,
    UPSERT_PATH,
    HubSpotClient,
    NullCrmClient,
)
from app.infrastructure.hubspot.mapper import CUSTOM_PROPERTIES, to_hubspot_properties

pytestmark = pytest.mark.unit

UPSERT_URL = f"{DEFAULT_BASE_URL}{UPSERT_PATH}"


def make_contact(is_demo: bool = False, phone: str | None = "+44 7700 900123") -> CrmContactUpsert:
    return CrmContactUpsert(
        email="sarah@example.com",
        first_name="Sarah",
        last_name="Morgan",
        company_name="Bloom Skin Clinic",
        phone=phone,
        website="https://bloom.example.com",
        industry="beauty",
        monthly_revenue="100k_500k",
        marketing_budget="10k_plus",
        content_volume="30_plus",
        primary_goal="lead_generation",
        start_timeline="immediately",
        lead_score=100,
        lead_temperature="hot",
        lead_source="website",
        is_demo=is_demo,
    )


async def call_with_response(response: httpx.Response) -> str:
    """Run one upsert against a mocked HubSpot and return the contact id."""
    async with httpx.AsyncClient() as http:
        client = HubSpotClient(access_token="token", http_client=http)
        with respx.mock:
            respx.post(UPSERT_URL).mock(return_value=response)
            ref = await client.upsert_contact(make_contact())
            return ref.contact_id


async def expect_error(response: httpx.Response) -> Exception:
    async with httpx.AsyncClient() as http:
        client = HubSpotClient(access_token="token", http_client=http)
        with respx.mock:
            respx.post(UPSERT_URL).mock(return_value=response)
            with pytest.raises((CrmTransientError, CrmPermanentError)) as info:
                await client.upsert_contact(make_contact())
            return info.value


# --- success ----------------------------------------------------------------


async def test_a_successful_upsert_returns_the_contact_id() -> None:
    contact_id = await call_with_response(httpx.Response(200, json={"results": [{"id": "12345"}]}))
    assert contact_id == "12345"


async def test_the_upsert_is_keyed_on_email() -> None:
    """HubSpot's batch upsert with idProperty=email is natively idempotent.

    That choice is what stops at-least-once outbox delivery from producing
    duplicate contacts, and it is worth pinning down in a test.
    """
    async with httpx.AsyncClient() as http:
        client = HubSpotClient(access_token="token", http_client=http)
        with respx.mock:
            route = respx.post(UPSERT_URL).mock(
                return_value=httpx.Response(200, json={"results": [{"id": "1"}]})
            )
            await client.upsert_contact(make_contact())

    body = route.calls[0].request.content.decode()
    assert '"idProperty":"email"' in body.replace(" ", "")
    assert "sarah@example.com" in body


async def test_the_token_is_sent_as_a_bearer_header() -> None:
    async with httpx.AsyncClient() as http:
        client = HubSpotClient(access_token="secret-token", http_client=http)
        with respx.mock:
            route = respx.post(UPSERT_URL).mock(
                return_value=httpx.Response(200, json={"results": [{"id": "1"}]})
            )
            await client.upsert_contact(make_contact())

    assert route.calls[0].request.headers["Authorization"] == "Bearer secret-token"


# --- error classification: the retry policy ---------------------------------


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 422])
async def test_client_errors_are_permanent(status_code: int) -> None:
    """Retrying these forever changes nothing except the size of the queue."""
    error = await expect_error(httpx.Response(status_code, json={"message": "nope"}))
    assert isinstance(error, CrmPermanentError)


@pytest.mark.parametrize("status_code", [408, 429, 500, 502, 503, 504])
async def test_server_and_throttle_errors_are_transient(status_code: int) -> None:
    error = await expect_error(httpx.Response(status_code, json={"message": "later"}))
    assert isinstance(error, CrmTransientError)


async def test_a_retry_after_header_is_honoured() -> None:
    """Retrying sooner than a rate limiter asked turns a short throttle into a
    long one."""
    error = await expect_error(
        httpx.Response(429, headers={"Retry-After": "90"}, json={"message": "slow"})
    )
    assert isinstance(error, CrmTransientError)
    assert error.retry_after_seconds == 90


async def test_a_nonsense_retry_after_is_ignored_not_trusted() -> None:
    error = await expect_error(
        httpx.Response(429, headers={"Retry-After": "not-a-number"}, json={})
    )
    assert isinstance(error, CrmTransientError)
    assert error.retry_after_seconds is None


async def test_a_huge_retry_after_is_clamped() -> None:
    """A malformed or hostile header must not park an event for a week."""
    error = await expect_error(httpx.Response(429, headers={"Retry-After": "999999"}, json={}))
    assert isinstance(error, CrmTransientError)
    assert error.retry_after_seconds == 3600


async def test_a_timeout_is_transient() -> None:
    async with httpx.AsyncClient() as http:
        client = HubSpotClient(access_token="token", http_client=http)
        with respx.mock:
            respx.post(UPSERT_URL).mock(side_effect=httpx.ConnectTimeout("timed out"))
            with pytest.raises(CrmTransientError):
                await client.upsert_contact(make_contact())


async def test_a_connection_failure_is_transient() -> None:
    async with httpx.AsyncClient() as http:
        client = HubSpotClient(access_token="token", http_client=http)
        with respx.mock:
            respx.post(UPSERT_URL).mock(side_effect=httpx.ConnectError("refused"))
            with pytest.raises(CrmTransientError):
                await client.upsert_contact(make_contact())


async def test_the_error_message_never_leaks_the_token() -> None:
    """Error strings are stored in the database and rendered on the dashboard."""
    error = await expect_error(httpx.Response(401, json={"message": "bad auth"}))
    assert "secret" not in str(error).lower()
    assert "bearer" not in str(error).lower()


async def test_an_unexpected_response_shape_does_not_crash() -> None:
    """A change in HubSpot's response format should degrade, not except."""
    assert await call_with_response(httpx.Response(200, json={})) == "unknown"


# --- not configured ---------------------------------------------------------


async def test_an_unconfigured_client_refuses_rather_than_guessing() -> None:
    async with httpx.AsyncClient() as http:
        client = HubSpotClient(access_token=None, http_client=http)
        assert client.is_configured is False
        with pytest.raises(CrmNotConfiguredError):
            await client.upsert_contact(make_contact())


async def test_the_null_client_reports_itself_unconfigured() -> None:
    """Running with no CRM is a supported production mode, not a stub."""
    client = NullCrmClient()
    assert client.is_configured is False
    with pytest.raises(CrmNotConfiguredError):
        await client.upsert_contact(make_contact())


# --- the anti-corruption layer ----------------------------------------------


def test_the_mapper_translates_into_hubspot_property_names() -> None:
    """This is the one file allowed to know the word "firstname"."""
    properties = to_hubspot_properties(make_contact())
    assert properties["firstname"] == "Sarah"
    assert properties["lastname"] == "Morgan"
    assert properties["company"] == "Bloom Skin Clinic"
    assert properties["fluxframe_lead_score"] == "100"
    assert properties["fluxframe_lead_temperature"] == "hot"


def test_demo_leads_are_always_flagged_in_the_crm() -> None:
    assert to_hubspot_properties(make_contact(is_demo=True))["fluxframe_demo_lead"] == "true"
    assert to_hubspot_properties(make_contact())["fluxframe_demo_lead"] == "false"


def test_empty_optionals_are_omitted_rather_than_blanked() -> None:
    """HubSpot treats an empty string as "clear this field", which would wipe a
    phone number the sales team added by hand."""
    assert "phone" not in to_hubspot_properties(make_contact(phone=None))
    assert "phone" in to_hubspot_properties(make_contact(phone="123"))


def test_every_custom_property_sent_is_one_the_bootstrap_script_creates() -> None:
    """A property we send but never create is a guaranteed 400 in production."""
    sent = {key for key in to_hubspot_properties(make_contact()) if key.startswith("fluxframe_")}
    assert sent <= set(CUSTOM_PROPERTIES)
