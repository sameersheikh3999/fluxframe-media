"""Contract tests for the public lead endpoint.

These go through the real ASGI application: middleware, validation, the
composition root, the service, the domain and a real database. What they pin
down is the *contract* — status codes, response shapes, error envelopes — which
is what the frontend depends on and what an OpenAPI-generated client reflects.
"""

from typing import Any

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def test_a_valid_submission_returns_201_with_an_id(
    client: AsyncClient, valid_lead_payload: dict[str, Any]
) -> None:
    response = await client.post("/api/v1/leads", json=valid_lead_payload)

    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["created_at"]
    assert "Thanks" in body["message"]


async def test_the_public_response_never_leaks_the_score(
    client: AsyncClient, valid_lead_payload: dict[str, Any]
) -> None:
    """A prospect must not learn we rated them COLD, and exposing the scoring
    internals would let anyone reverse-engineer the rules."""
    body = (await client.post("/api/v1/leads", json=valid_lead_payload)).json()

    assert "score" not in body
    assert "temperature" not in body
    assert "score_breakdown" not in body
    assert "crm_sync_status" not in body


async def test_the_second_identical_submission_returns_200_not_an_error(
    client: AsyncClient, valid_lead_payload: dict[str, Any]
) -> None:
    """The double-click case. Both succeed from the visitor's point of view;
    the status code tells an API consumer nothing new was created."""
    first = await client.post("/api/v1/leads", json=valid_lead_payload)
    second = await client.post("/api/v1/leads", json=valid_lead_payload)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


async def test_the_idempotency_key_can_come_from_the_header(
    client: AsyncClient, valid_lead_payload: dict[str, Any]
) -> None:
    """`Idempotency-Key` is the HTTP-native spelling and wins over the body."""
    first = await client.post(
        "/api/v1/leads",
        json=valid_lead_payload,
        headers={"Idempotency-Key": "header-key-123456"},
    )
    second = await client.post(
        "/api/v1/leads",
        json={**valid_lead_payload, "idempotency_key": "a-different-one"},
        headers={"Idempotency-Key": "header-key-123456"},
    )

    assert first.status_code == 201
    assert second.status_code == 200


# --- validation -------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("email", "not-an-email"),
        ("industry", "underwater_basket_weaving"),
        ("monthly_marketing_budget", "a_lot"),
        ("content_volume", "17"),
        ("primary_goal", "world_domination"),
        ("start_timeline", "yesterday"),
    ],
)
async def test_invalid_values_are_rejected_with_a_structured_error(
    client: AsyncClient, valid_lead_payload: dict[str, Any], field: str, value: str
) -> None:
    response = await client.post("/api/v1/leads", json={**valid_lead_payload, field: value})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert any(detail["field"] == field for detail in error["details"])


async def test_a_missing_required_field_is_rejected(
    client: AsyncClient, valid_lead_payload: dict[str, Any]
) -> None:
    payload = {**valid_lead_payload}
    del payload["company_name"]
    response = await client.post("/api/v1/leads", json=payload)
    assert response.status_code == 422


async def test_unknown_fields_are_rejected(
    client: AsyncClient, valid_lead_payload: dict[str, Any]
) -> None:
    """`extra="forbid"`. A typo'd field name should fail loudly, not silently
    drop the value the user typed."""
    response = await client.post("/api/v1/leads", json={**valid_lead_payload, "budget": "lots"})
    assert response.status_code == 422


async def test_an_oversized_message_is_rejected(
    client: AsyncClient, valid_lead_payload: dict[str, Any]
) -> None:
    response = await client.post(
        "/api/v1/leads", json={**valid_lead_payload, "message": "x" * 6000}
    )
    assert response.status_code == 422


async def test_a_website_without_a_scheme_is_normalised(
    client: AsyncClient, valid_lead_payload: dict[str, Any]
) -> None:
    """People do not type "https://". Rejecting them for it would lose leads."""
    created = await client.post("/api/v1/leads", json={**valid_lead_payload, "website": "acme.com"})
    assert created.status_code == 201

    detail = await client.get(f"/api/v1/dashboard/leads/{created.json()['id']}")
    assert detail.json()["website"] == "https://acme.com"


# --- the shared error envelope ----------------------------------------------


async def test_every_error_uses_the_same_envelope(client: AsyncClient) -> None:
    """One shape means the frontend writes one error handler."""
    response = await client.get("/api/v1/leads/nope")

    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details", "request_id"}


async def test_errors_carry_the_request_id_for_support(client: AsyncClient) -> None:
    response = await client.post("/api/v1/leads", json={})
    assert response.json()["error"]["request_id"]
    assert response.headers["X-Request-ID"]


# --- scoring reaches the dashboard ------------------------------------------


async def test_a_captured_lead_is_scored_and_visible_on_the_dashboard(
    client: AsyncClient, valid_lead_payload: dict[str, Any]
) -> None:
    """The full public-to-internal path in one test."""
    created = await client.post("/api/v1/leads", json=valid_lead_payload)
    lead_id = created.json()["id"]

    detail = (await client.get(f"/api/v1/dashboard/leads/{lead_id}")).json()

    assert detail["score"] == 100
    assert detail["temperature"] == "hot"
    assert detail["score_version"] == "v1"
    assert len(detail["score_breakdown"]["components"]) == 5
    assert detail["status"] == "new"
    assert detail["crm_sync_status"] == "pending"
    # Captured + scored.
    assert len(detail["activities"]) == 2
