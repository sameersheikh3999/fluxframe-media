"""Port: checking whether one external dependency is usable.

Each external system Fluxframe depends on gets a probe. Phase 0 has a single
placeholder probe because there is no database yet; Phase 1 replaces it with one
that runs ``SELECT 1``, and the readiness endpoint does not change at all.

That non-change is the point of the port.
"""

from typing import Protocol

from app.application.dto.system import DependencyStatus


class ReadinessProbe(Protocol):
    """Reports whether one dependency is ready to be used."""

    async def check(self) -> DependencyStatus:
        """Probe the dependency.

        Must not raise. A probe that cannot reach its dependency reports
        ``DependencyState.FAILED`` — an exception escaping here would turn a
        degraded dependency into a broken health endpoint.
        """
        ...
