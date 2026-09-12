"""Port: reading the current time.

Time is an external dependency, exactly like a database. A use case that calls
``datetime.now()`` directly cannot be tested deterministically, and once Phase 5
introduces retry backoff ("try again in 2, 4, 8, 16 seconds") that stops being a
theoretical concern and starts costing real seconds in the test suite.

Adapters:
    app.infrastructure.clock.SystemClock   real wall-clock time
    tests.fakes.FrozenClock                a fixed instant, for tests
"""

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Supplies the current time as a timezone-aware UTC datetime."""

    def now(self) -> datetime:
        """Return the current instant. Always timezone-aware, always UTC."""
        ...
