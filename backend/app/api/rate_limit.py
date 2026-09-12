"""A small in-process rate limiter for the public lead endpoint.

Deliberately the simplest thing that solves the actual problem: stopping a bot
or a stuck retry loop from filling the database with junk leads.

**What it is:** a fixed-window counter per client IP, held in a dict in this
process.

**What it is not:** a distributed rate limiter. With two Railway replicas the
effective limit doubles, because each process counts separately. That is an
accepted trade, and it is worth being explicit about why: a shared limiter means
adding Redis — a new service, a new failure mode, a new bill — to buy precision
that a portfolio site does not need. If this ever protects something that
matters, the upgrade path is Redis with the same interface, or the rate limiting
built into a CDN in front of the app.

**Why not slowapi or a similar library:** it is forty lines, and a dependency
that does forty lines is a dependency you still have to understand, plus one you
have to keep updated.
"""

import time
from collections import defaultdict
from threading import Lock

from fastapi import HTTPException, Request, status

from app.config.settings import Settings

#: ip -> (window_started_at, count)
_BUCKETS: dict[str, tuple[float, int]] = defaultdict(lambda: (0.0, 0))
_LOCK = Lock()

#: Stop the dict growing without bound if the process runs for months. Cleared
#: wholesale rather than pruned per entry: an occasional reset that lets a few
#: requests through is cheaper than tracking expiry for every key.
_MAX_TRACKED_CLIENTS = 10_000


def client_identifier(request: Request) -> str:
    """Best-effort client identity.

    Behind Railway's proxy the socket address is the proxy, so `X-Forwarded-For`
    is the only useful signal. Its first entry is the original client.

    This header is trivially spoofable, which is exactly why it is used for rate
    limiting and nothing else — never for authentication, and never stored.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(request: Request, settings: Settings) -> None:
    """Raise 429 if this client has exceeded its window allowance."""
    if not settings.rate_limit_enabled:
        return

    identity = client_identifier(request)
    now = time.monotonic()
    window = float(settings.rate_limit_window_seconds)

    with _LOCK:
        if len(_BUCKETS) > _MAX_TRACKED_CLIENTS:
            _BUCKETS.clear()

        started_at, count = _BUCKETS[identity]
        if now - started_at >= window:
            _BUCKETS[identity] = (now, 1)
            return

        if count >= settings.rate_limit_requests:
            retry_after = max(1, int(window - (now - started_at)))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    "Too many submissions from this address. "
                    f"Please try again in {retry_after} seconds."
                ),
                headers={"Retry-After": str(retry_after)},
            )

        _BUCKETS[identity] = (started_at, count + 1)


def reset_rate_limits() -> None:
    """Clear all counters. Used by the test suite between cases."""
    with _LOCK:
        _BUCKETS.clear()
