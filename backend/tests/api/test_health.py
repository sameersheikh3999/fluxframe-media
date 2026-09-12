"""Contract tests for the health endpoints.

Liveness and readiness answer different questions, and conflating them is how a
database blip turns into a container crash loop. These tests pin the difference
down.
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


# --- the platform health check ----------------------------------------------


async def test_the_bare_health_endpoint_is_public_and_trivial(
    client: AsyncClient,
) -> None:
    """`GET /health` is what Railway probes.

    Unauthenticated, dependency-free and always cheap: it answers "is this
    process up", which is the only question a restart policy should act on.
    """
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_the_root_path_points_at_the_docs(client: AsyncClient) -> None:
    body = (await client.get("/")).json()
    assert body["docs"] == "/docs"
    assert body["health"] == "/health"


# --- liveness ---------------------------------------------------------------


async def test_liveness_reports_the_service_identity(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "Fluxframe Media API"
    assert body["environment"] == "local"
    assert body["checked_at"]


async def test_liveness_echoes_a_caller_supplied_request_id(
    client: AsyncClient,
) -> None:
    """A trace id from the Next.js server must survive into this backend."""
    response = await client.get("/api/v1/health", headers={"X-Request-ID": "trace-abc-123"})
    assert response.headers["X-Request-ID"] == "trace-abc-123"


async def test_liveness_generates_a_request_id_when_none_is_supplied(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/health")
    assert len(response.headers["X-Request-ID"]) == 32


# --- readiness --------------------------------------------------------------


async def test_readiness_probes_the_real_database(client: AsyncClient) -> None:
    """With a database configured, the probe actually runs SELECT 1."""
    response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"

    checks = {check["name"]: check for check in body["checks"]}
    assert checks["database"]["state"] == "ok"


async def test_readiness_reports_unconfigured_integrations_honestly(
    client: AsyncClient,
) -> None:
    """ "Not configured" is a supported mode, not a failure.

    Only a genuinely FAILED dependency makes the service unready — an
    unconfigured CRM does not stop it serving every route it has.
    """
    body = (await client.get("/api/v1/health/ready")).json()
    checks = {check["name"]: check for check in body["checks"]}

    assert checks["hubspot"]["state"] == "not_configured"
    assert "HUBSPOT_ACCESS_TOKEN" in checks["hubspot"]["detail"]
    assert checks["ai"]["state"] == "not_configured"
    assert "ANTHROPIC_API_KEY" in checks["ai"]["detail"]

    # Still ready: the site works perfectly well without either.
    assert body["status"] == "ready"


# --- errors -----------------------------------------------------------------


async def test_unknown_route_uses_the_shared_error_envelope(
    client: AsyncClient,
) -> None:
    """Every failure in this API has the same shape, including 404s."""
    response = await client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "http_404"
    assert body["error"]["request_id"] is not None
