"""DTOs describing the health and readiness of the running service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class DependencyState(StrEnum):
    """The outcome of probing one external dependency."""

    OK = "ok"
    #: The dependency is not wired up yet. Expected in Phase 0: there is no
    #: database. This is distinct from FAILED, which means we tried and lost.
    NOT_CONFIGURED = "not_configured"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class DependencyStatus:
    """The result of a single readiness probe."""

    name: str
    state: DependencyState
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class HealthReport:
    """Liveness: is this process running and able to answer?

    Deliberately answers without touching any external system, because this is
    what the platform health check calls. A liveness probe that depends on the
    database will restart a perfectly healthy container during a database blip.
    """

    service: str
    version: str
    environment: str
    checked_at: datetime


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    """Readiness: can this process actually serve traffic right now?"""

    ready: bool
    checks: tuple[DependencyStatus, ...]
    checked_at: datetime
