"""Contract tests for the health endpoints."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.unit


async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "Fluxframe Media API"
    assert body["environment"] == "local"
    assert "checked_at" in body


async def test_health_echoes_a_caller_supplied_request_id(client: AsyncClient) -> None:
    """A trace id from the Next.js server must survive into this backend."""
    response = await client.get("/api/v1/health", headers={"X-Request-ID": "trace-abc-123"})

    assert response.headers["X-Request-ID"] == "trace-abc-123"


async def test_health_generates_a_request_id_when_none_is_supplied(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert len(response.headers["X-Request-ID"]) == 32


async def test_readiness_reports_the_database_as_not_configured(client: AsyncClient) -> None:
    """Phase 0 has no database. The endpoint says so rather than guessing."""
    response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == [
        {
            "name": "database",
            "state": "not_configured",
            "detail": "No database is configured yet; this arrives in Phase 1.",
        }
    ]


async def test_unknown_route_uses_the_shared_error_envelope(client: AsyncClient) -> None:
    """Every failure in this API has the same shape, including 404s."""
    response = await client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "http_404"
    assert body["error"]["request_id"] is not None
