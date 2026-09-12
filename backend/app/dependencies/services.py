"""Providers that FastAPI's Depends() resolves.

Each function here answers one question: "when something asks for X, what does
it actually get?"

Note what these functions return. ``get_clock`` is annotated ``-> Clock`` — the
port — while constructing a ``SystemClock`` — the adapter. mypy checks at this
line, and only at this line, that SystemClock satisfies the Clock Protocol. If
someone changes ``SystemClock.now()`` to return a string, the error surfaces
here, in the composition root, rather than at runtime in production.
"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.application.ports.clock import Clock
from app.application.ports.readiness_probe import ReadinessProbe
from app.application.services.system_service import SystemService
from app.config.settings import Settings, get_settings
from app.infrastructure.clock import SystemClock
from app.infrastructure.readiness.not_configured_probe import NotConfiguredProbe

SettingsDep = Annotated[Settings, Depends(get_settings)]


@lru_cache
def get_clock() -> Clock:
    """The application's source of time.

    Cached because SystemClock is stateless — one instance is plenty.
    """
    return SystemClock()


def get_readiness_probes() -> list[ReadinessProbe]:
    """Every external dependency whose availability we report on.

    Phase 0 returns a single placeholder: there is no database to probe yet.
    Phase 1 replaces this line with a probe that runs SELECT 1 against Neon.
    Nothing above this function needs to know that happened.
    """
    return [
        NotConfiguredProbe(
            name="database",
            detail="No database is configured yet; this arrives in Phase 1.",
        )
    ]


def get_system_service(
    settings: SettingsDep,
    clock: Annotated[Clock, Depends(get_clock)],
    probes: Annotated[list[ReadinessProbe], Depends(get_readiness_probes)],
) -> SystemService:
    """Assemble SystemService from its ports and the deployment settings.

    The service receives three plain strings rather than the Settings object
    itself. That keeps app.application free of any knowledge that a settings
    system exists at all — and it is what lets the unit test construct a
    SystemService without an environment.
    """
    return SystemService(
        clock=clock,
        probes=probes,
        service_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment.value,
    )


SystemServiceDep = Annotated[SystemService, Depends(get_system_service)]
