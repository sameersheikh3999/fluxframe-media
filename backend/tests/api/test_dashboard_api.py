"""Contract tests for the internal dashboard, demo and admin endpoints.

The first thing these check is that the endpoints are actually protected. An
internal endpoint that quietly works without its secret is worse than no
protection at all, because nobody notices.
"""

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration


# --- access control ---------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/dashboard/stats"),
        ("GET", "/api/v1/dashboard/leads"),
        ("POST", "/api/v1/demo/leads"),
        ("POST", "/api/v1/admin/outbox/dispatch"),
    ],
)
async def test_internal_endpoints_reject_a_missing_secret(
    app: FastAPI, method: str, path: str
) -> None:
    """No header, no access. The browser never holds this secret — only the
    Next.js server does, which is why dashboard pages render server-side."""
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://testserver") as anonymous,
        app.router.lifespan_context(app),
    ):
        response = await anonymous.request(method, path, json={})

    assert response.status_code == 401


async def test_internal_endpoints_reject_a_wrong_secret(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={"X-Internal-Secret": "not-the-secret"},
        ) as impostor,
        app.router.lifespan_context(app),
    ):
        response = await impostor.get("/api/v1/dashboard/stats")

    assert response.status_code == 401


async def test_the_public_lead_endpoint_needs_no_secret(app: FastAPI) -> None:
    """The marketing form is called by anonymous browsers. It must stay open."""
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://testserver") as anonymous,
        app.router.lifespan_context(app),
    ):
        # Empty body -> 422 from validation, NOT 401 from auth.
        response = await anonymous.post("/api/v1/leads", json={})

    assert response.status_code == 422


# --- stats and listing ------------------------------------------------------


async def test_stats_start_empty(client: AsyncClient) -> None:
    stats = (await client.get("/api/v1/dashboard/stats")).json()
    assert stats["total_leads"] == 0
    assert stats["outbox_pending"] == 0


async def test_stats_count_captured_leads(
    client: AsyncClient, valid_lead_payload: dict[str, Any]
) -> None:
    await client.post("/api/v1/leads", json=valid_lead_payload)

    stats = (await client.get("/api/v1/dashboard/stats")).json()

    assert stats["total_leads"] == 1
    assert stats["hot_leads"] == 1
    assert stats["crm_sync_pending"] == 1
    # Two events written in the same transaction as the lead.
    assert stats["outbox_pending"] == 2


async def test_listing_is_paginated(
    client: AsyncClient, valid_lead_payload: dict[str, Any]
) -> None:
    for index in range(3):
        await client.post(
            "/api/v1/leads",
            json={
                **valid_lead_payload,
                "idempotency_key": f"page-key-{index:04d}",
                "email": f"lead{index}@example.com",
            },
        )

    page = (await client.get("/api/v1/dashboard/leads?limit=2")).json()

    assert page["total"] == 3
    assert len(page["items"]) == 2
    assert page["has_more"] is True


async def test_listing_can_be_filtered_by_temperature(
    client: AsyncClient, valid_lead_payload: dict[str, Any]
) -> None:
    await client.post("/api/v1/leads", json=valid_lead_payload)

    hot = (await client.get("/api/v1/dashboard/leads?temperature=hot")).json()
    cold = (await client.get("/api/v1/dashboard/leads?temperature=cold")).json()

    assert hot["total"] == 1
    assert cold["total"] == 0


async def test_an_oversized_limit_is_rejected(client: AsyncClient) -> None:
    """`?limit=100000` is a denial-of-service vector that costs one keystroke."""
    assert (await client.get("/api/v1/dashboard/leads?limit=100000")).status_code == 422


# --- lifecycle transitions --------------------------------------------------


async def test_a_legal_transition_is_applied(
    client: AsyncClient, valid_lead_payload: dict[str, Any]
) -> None:
    lead_id = (await client.post("/api/v1/leads", json=valid_lead_payload)).json()["id"]

    response = await client.patch(
        f"/api/v1/dashboard/leads/{lead_id}/status",
        json={"status": "qualified", "actor": "user:sam"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "qualified"


async def test_an_illegal_transition_is_rejected_by_the_domain(
    client: AsyncClient, valid_lead_payload: dict[str, Any]
) -> None:
    """NEW -> WON skips the pipeline. The entity refuses, and the API surfaces
    that as a structured 422 rather than a 500."""
    lead_id = (await client.post("/api/v1/leads", json=valid_lead_payload)).json()["id"]

    response = await client.patch(
        f"/api/v1/dashboard/leads/{lead_id}/status", json={"status": "won"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "illegal_lead_transition"


async def test_the_detail_page_lists_only_legal_next_statuses(
    client: AsyncClient, valid_lead_payload: dict[str, Any]
) -> None:
    """The UI asks the domain which buttons to render, so it cannot offer a
    transition the entity would reject."""
    lead_id = (await client.post("/api/v1/leads", json=valid_lead_payload)).json()["id"]

    detail = (await client.get(f"/api/v1/dashboard/leads/{lead_id}")).json()

    assert "qualified" in detail["allowed_next_statuses"]
    assert "won" not in detail["allowed_next_statuses"]


async def test_a_missing_lead_returns_404_with_the_shared_envelope(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/dashboard/leads/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "lead_not_found"


async def test_rescoring_is_available_and_logged(
    client: AsyncClient, valid_lead_payload: dict[str, Any]
) -> None:
    lead_id = (await client.post("/api/v1/leads", json=valid_lead_payload)).json()["id"]

    detail = (await client.post(f"/api/v1/dashboard/leads/{lead_id}/rescore")).json()

    assert detail["score"] == 100
    assert sum(1 for a in detail["activities"] if a["activity_type"] == "scored") == 2


# --- AI --------------------------------------------------------------------


async def test_the_sales_brief_endpoint_reports_unavailable_without_a_key(
    client: AsyncClient, valid_lead_payload: dict[str, Any]
) -> None:
    """No ANTHROPIC_API_KEY in the test environment.

    It must say so clearly rather than fabricating a brief — an invented brief
    would be worse than none, because a salesperson would act on it.
    """
    lead_id = (await client.post("/api/v1/leads", json=valid_lead_payload)).json()["id"]

    response = await client.post(f"/api/v1/dashboard/leads/{lead_id}/sales-brief")

    assert response.status_code == 503
    body = response.json()["error"]
    assert body["code"] == "ai_unavailable"
    assert "ANTHROPIC_API_KEY" in body["message"]


# --- demo generator ---------------------------------------------------------


async def test_generating_demo_leads_creates_real_scored_leads(
    client: AsyncClient,
) -> None:
    """Synthetic leads go through the SAME service as the public form, so they
    are genuinely scored and genuinely produce outbox events."""
    response = await client.post(
        "/api/v1/demo/leads", json={"count": 5, "quality": "mostly_hot", "seed": 42}
    )

    assert response.status_code == 201
    body = response.json()
    assert len(body["generated"]) == 5

    stats = (await client.get("/api/v1/dashboard/stats")).json()
    assert stats["total_leads"] == 5
    assert stats["demo_leads"] == 5
    assert stats["outbox_pending"] > 0


async def test_every_demo_lead_uses_a_reserved_email_domain(
    client: AsyncClient,
) -> None:
    """Non-negotiable: @example.com is RFC 2606 reserved and cannot route."""
    body = (await client.post("/api/v1/demo/leads", json={"count": 8})).json()
    assert all(item["email"].endswith("@example.com") for item in body["generated"])


async def test_demo_leads_are_flagged_as_demo(client: AsyncClient) -> None:
    await client.post("/api/v1/demo/leads", json={"count": 3})
    page = (await client.get("/api/v1/dashboard/leads")).json()
    assert all(item["is_demo"] for item in page["items"])
    assert all(item["source"] == "demo_generator" for item in page["items"])


async def test_a_batch_larger_than_the_cap_is_rejected(client: AsyncClient) -> None:
    response = await client.post("/api/v1/demo/leads", json={"count": 50})
    assert response.status_code == 422


async def test_the_same_seed_produces_the_same_batch(client: AsyncClient) -> None:
    first = (await client.post("/api/v1/demo/leads", json={"count": 3, "seed": 7})).json()
    second = (await client.post("/api/v1/demo/leads", json={"count": 3, "seed": 7})).json()

    names_a = [item["full_name"] for item in first["generated"]]
    names_b = [item["full_name"] for item in second["generated"]]
    assert names_a == names_b
    # ...but the emails differ, so the two batches are distinct leads rather
    # than a deduplicated replay.
    assert first["generated"][0]["email"] != second["generated"][0]["email"]


# --- outbox operations ------------------------------------------------------


async def test_dispatching_the_outbox_drains_it(
    client: AsyncClient, valid_lead_payload: dict[str, Any]
) -> None:
    """With no CRM configured, syncs are skipped — a supported mode — and the
    queue still drains rather than backing up."""
    await client.post("/api/v1/leads", json=valid_lead_payload)

    report = (await client.post("/api/v1/admin/outbox/dispatch")).json()

    assert report["claimed"] == 2
    assert report["processed"] + report["skipped"] == 2

    stats = (await client.get("/api/v1/dashboard/stats")).json()
    assert stats["outbox_pending"] == 0
    assert stats["outbox_dead_lettered"] == 0


async def test_after_dispatch_the_lead_shows_a_resolved_sync_status(
    client: AsyncClient, valid_lead_payload: dict[str, Any]
) -> None:
    lead_id = (await client.post("/api/v1/leads", json=valid_lead_payload)).json()["id"]

    await client.post("/api/v1/admin/outbox/dispatch")

    detail = (await client.get(f"/api/v1/dashboard/leads/{lead_id}")).json()
    assert detail["crm_sync_status"] == "skipped"
    assert any(a["activity_type"] == "crm_sync_skipped" for a in detail["activities"])


async def test_replaying_an_unknown_event_returns_404(client: AsyncClient) -> None:
    response = await client.post("/api/v1/admin/outbox/00000000-0000-0000-0000-000000000000/replay")
    assert response.status_code == 404
