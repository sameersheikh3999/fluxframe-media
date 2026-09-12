"""Health endpoints.

Two endpoints, deliberately different, because platforms ask two different
questions:

    GET /api/v1/health        Liveness. "Is this process alive?" Touches
                              nothing external. This is what Railway's health
                              check calls. A liveness probe that queries the
                              database will restart a healthy container during
                              a database blip — turning a small outage into a
                              crash loop.

    GET /api/v1/health/ready  Readiness. "Can this process serve traffic?"
                              Probes its dependencies. In Phase 0 there is
                              nothing to probe, so it reports the database as
                              `not_configured` rather than lying either way.

Notice the shape of both functions: receive the service, call one method, map
the DTO onto the response schema. No logic. That is the whole job of a router.
"""

from fastapi import APIRouter

from app.dependencies.services import SystemServiceDep
from app.schemas.health import (
    HealthResponse,
    ReadinessCheckResponse,
    ReadinessResponse,
)

router = APIRouter(prefix="/health", tags=["system"])


@router.get(
    "",
    response_model=HealthResponse,
    summary="Liveness probe",
    description="Returns 200 whenever the process is running. Performs no I/O.",
)
def health(service: SystemServiceDep) -> HealthResponse:
    """Synchronous on purpose — this path awaits nothing.

    FastAPI runs a plain `def` endpoint in a worker thread, which leaves the
    event loop free. Making it `async def` would be a small lie about what the
    function does, and this codebase would rather not tell small lies about
    concurrency.
    """
    report = service.health()
    return HealthResponse(
        service=report.service,
        version=report.version,
        environment=report.environment,
        checked_at=report.checked_at,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description=(
        "Reports whether every external dependency is usable. "
        "In Phase 0 the database is reported as `not_configured`, because there is not one yet."
    ),
)
async def readiness(service: SystemServiceDep) -> ReadinessResponse:
    """Asynchronous because real probes perform real I/O."""
    report = await service.readiness()
    return ReadinessResponse(
        status="ready" if report.ready else "not_ready",
        checks=[
            ReadinessCheckResponse(name=check.name, state=check.state.value, detail=check.detail)
            for check in report.checks
        ],
        checked_at=report.checked_at,
    )
