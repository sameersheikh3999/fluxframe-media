"""Unit tests for SystemService.

Look at what these tests do NOT need: no database, no HTTP client, no FastAPI
application, no environment file, no fixtures beyond the ones constructed on the
first line of each test. That is what the ports bought us, and it is the pattern
every service test from Phase 1 onward will follow.
"""

from datetime import UTC, datetime

import pytest

from app.application.dto.system import DependencyState
from app.application.services.system_service import SystemService
from tests.fakes import FrozenClock, StubProbe

pytestmark = pytest.mark.unit

FIXED_TIME = datetime(2026, 3, 1, 9, 30, 0, tzinfo=UTC)


def _service(*probes: StubProbe) -> SystemService:
    return SystemService(
        clock=FrozenClock(FIXED_TIME),
        probes=list(probes),
        service_name="Fluxframe Media API",
        version="0.1.0",
        environment="local",
    )


def test_health_reports_service_identity_and_the_injected_time() -> None:
    report = _service().health()

    assert report.service == "Fluxframe Media API"
    assert report.version == "0.1.0"
    assert report.environment == "local"
    # The time came from FrozenClock, not from the wall clock. This is the
    # whole reason the Clock port exists.
    assert report.checked_at == FIXED_TIME


async def test_readiness_is_ready_when_every_probe_is_ok() -> None:
    report = await _service(
        StubProbe("database", DependencyState.OK),
        StubProbe("hubspot", DependencyState.OK),
    ).readiness()

    assert report.ready is True
    assert [check.name for check in report.checks] == ["database", "hubspot"]


async def test_readiness_stays_ready_when_a_dependency_is_merely_unconfigured() -> None:
    """Phase 0's actual situation: no database wired up yet.

    'Not configured' is not 'broken'. The service can serve every route it has,
    so it must not report itself unready — an unready service is removed from
    the load balancer.
    """
    report = await _service(StubProbe("database", DependencyState.NOT_CONFIGURED)).readiness()

    assert report.ready is True
    assert report.checks[0].state is DependencyState.NOT_CONFIGURED


async def test_readiness_is_not_ready_when_any_probe_failed() -> None:
    report = await _service(
        StubProbe("database", DependencyState.OK),
        StubProbe("hubspot", DependencyState.FAILED, "connection refused"),
    ).readiness()

    assert report.ready is False


async def test_readiness_with_no_probes_is_ready() -> None:
    report = await _service().readiness()

    assert report.ready is True
    assert report.checks == ()
