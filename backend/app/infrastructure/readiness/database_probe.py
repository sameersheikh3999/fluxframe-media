"""Adapter: the real database readiness probe.

Replaces Phase 0's NotConfiguredProbe. Note what did NOT change when it did:
the router, SystemService and the response schema are untouched. That is the
port paying out.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.application.dto.system import DependencyState, DependencyStatus


class DatabaseReadinessProbe:
    """Runs SELECT 1 against the configured database."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def check(self) -> DependencyStatus:
        """Probe the database. Must never raise.

        An exception escaping here would turn a degraded dependency into a
        broken health endpoint — which is how a database blip becomes an
        outage of the thing that tells you about database blips.
        """
        try:
            async with self._engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception as exc:
            return DependencyStatus(
                name="database",
                state=DependencyState.FAILED,
                detail=f"{type(exc).__name__}: {str(exc)[:200]}",
            )
        return DependencyStatus(name="database", state=DependencyState.OK)


class CrmConfigurationProbe:
    """Reports whether the CRM integration is wired up.

    Never FAILED: an unconfigured CRM is a supported mode, not a fault, and
    reporting it as failed would take the service out of the load balancer for
    something that does not affect serving traffic.
    """

    def __init__(self, *, configured: bool) -> None:
        self._configured = configured

    async def check(self) -> DependencyStatus:
        if self._configured:
            return DependencyStatus(name="hubspot", state=DependencyState.OK)
        return DependencyStatus(
            name="hubspot",
            state=DependencyState.NOT_CONFIGURED,
            detail="HUBSPOT_ACCESS_TOKEN is not set; CRM syncs are skipped.",
        )


class AiConfigurationProbe:
    """Reports whether an AI provider is wired up. Never FAILED, same reason."""

    def __init__(self, *, configured: bool) -> None:
        self._configured = configured

    async def check(self) -> DependencyStatus:
        if self._configured:
            return DependencyStatus(name="ai", state=DependencyState.OK)
        return DependencyStatus(
            name="ai",
            state=DependencyState.NOT_CONFIGURED,
            detail="ANTHROPIC_API_KEY is not set; AI sales briefs are disabled.",
        )
