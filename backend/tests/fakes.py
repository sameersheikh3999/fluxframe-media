"""Test doubles satisfying the application's ports.

Note that none of these inherit from anything. They are ordinary classes that
happen to have the right methods, which is all a ``typing.Protocol`` requires.
That is the practical payoff of choosing Protocol over ABC: a fake is five
lines, not an inheritance ceremony.
"""

from datetime import UTC, datetime

from app.application.dto.system import DependencyState, DependencyStatus


class FrozenClock:
    """A clock that does not move. Satisfies app.application.ports.clock.Clock."""

    def __init__(self, instant: datetime | None = None) -> None:
        self._instant = instant or datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._instant


class StubProbe:
    """A readiness probe with a predetermined answer."""

    def __init__(self, name: str, state: DependencyState, detail: str | None = None) -> None:
        self._status = DependencyStatus(name=name, state=state, detail=detail)

    async def check(self) -> DependencyStatus:
        return self._status
