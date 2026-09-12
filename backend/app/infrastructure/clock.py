"""Adapter: the real system clock.

Satisfies app.application.ports.clock.Clock — structurally, without importing
it. That is Protocol conformance: this class has a ``now()`` returning a
``datetime`` and is therefore a ``Clock``, whether or not it has ever heard of
one. mypy checks that claim where the two meet, in app/dependencies/services.py.

Always timezone-aware UTC. Naive datetimes are the source of an entire genre of
bug that is tedious to find and trivial to prevent.
"""

from datetime import UTC, datetime


class SystemClock:
    """Reads the host's wall clock."""

    def now(self) -> datetime:
        return datetime.now(UTC)
