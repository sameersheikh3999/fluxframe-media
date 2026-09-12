"""Adapter: a probe for a dependency that does not exist yet.

Phase 0 has no database, so `/api/v1/health/ready` reports the database as
NOT_CONFIGURED rather than pretending it is fine or pretending it is broken.

This file is small, real and honest, and it earns its place by proving the
seam: in Phase 1 a ``DatabaseReadinessProbe`` running ``SELECT 1`` replaces it
in app/dependencies/services.py, and neither the router, the response schema
nor SystemService changes by a single character.
"""

from app.application.dto.system import DependencyState, DependencyStatus


class NotConfiguredProbe:
    """Reports a named dependency as deliberately not wired up yet."""

    def __init__(self, *, name: str, detail: str) -> None:
        self._name = name
        self._detail = detail

    async def check(self) -> DependencyStatus:
        return DependencyStatus(
            name=self._name,
            state=DependencyState.NOT_CONFIGURED,
            detail=self._detail,
        )
