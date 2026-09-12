"""Use cases for reporting on the running service itself.

This is the only service in Phase 0, and it exists for a reason beyond the two
endpoints it serves: it is a complete, working example of the dependency rule,
with no business logic to distract from it.

Read its constructor. It receives a Clock and a sequence of ReadinessProbes —
both Protocols from app.application.ports — plus three plain strings describing
the deployment. It does not import Settings, does not import FastAPI, does not
import anything from app.infrastructure. Everything it needs arrives from
outside, chosen by the composition root in app/dependencies/services.py.

That is why it can be unit-tested in microseconds with no fixtures at all.
"""

from collections.abc import Sequence

from app.application.dto.system import (
    DependencyState,
    HealthReport,
    ReadinessReport,
)
from app.application.ports.clock import Clock
from app.application.ports.readiness_probe import ReadinessProbe


class SystemService:
    """Answers 'is this process alive?' and 'can it serve traffic?'."""

    def __init__(
        self,
        *,
        clock: Clock,
        probes: Sequence[ReadinessProbe],
        service_name: str,
        version: str,
        environment: str,
    ) -> None:
        self._clock = clock
        self._probes = tuple(probes)
        self._service_name = service_name
        self._version = version
        self._environment = environment

    def health(self) -> HealthReport:
        """Liveness. Synchronous on purpose: it performs no I/O whatsoever.

        FastAPI will run a plain ``def`` endpoint in a worker thread, which for
        a function this cheap is pure overhead — but the honesty is worth more
        than the microseconds. Marking this ``async`` would imply it awaits
        something, and it does not. Not every function in an async application
        needs to be a coroutine.
        """
        return HealthReport(
            service=self._service_name,
            version=self._version,
            environment=self._environment,
            checked_at=self._clock.now(),
        )

    async def readiness(self) -> ReadinessReport:
        """Readiness. Asynchronous because probes perform real I/O.

        A dependency reporting NOT_CONFIGURED does not make the service
        unready. In Phase 0 there is no database, and the service can still
        serve every route it has. Only an outright FAILED probe means 'do not
        send me traffic'.
        """
        results = [await probe.check() for probe in self._probes]
        checks = tuple(results)
        ready = all(check.state is not DependencyState.FAILED for check in checks)
        return ReadinessReport(
            ready=ready,
            checks=checks,
            checked_at=self._clock.now(),
        )
