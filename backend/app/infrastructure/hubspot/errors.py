"""Classifying HubSpot responses into retryable and non-retryable failures.

This is a small file that does a disproportionate amount of work. The whole
retry policy — how long the queue holds an event, whether a dead letter appears
on the dashboard, whether a wrong token is noticed in minutes or never — comes
down to which branch a response takes here.

    429              transient   rate limited. Honour Retry-After.
    5xx              transient   HubSpot's problem, will pass.
    timeout / conn   transient   the network. Retry.
    408              transient   request timeout, server side.
    400 / 422        permanent   our payload is wrong (usually a missing custom
                                 property). Retrying identical bad data forever
                                 changes nothing except the size of the queue.
    401 / 403        permanent   the token is wrong, expired or lacks a scope.
                                 Retrying hides a config bug behind a queue that
                                 quietly grows. It must surface as a dead letter.
    404              permanent   endpoint or object does not exist.
    anything else    transient   optimism is safer: an unknown failure that is
                                 actually permanent still dies after
                                 max_attempts, whereas treating unknowns as
                                 permanent drops recoverable work on one blip.
"""

import httpx

from app.application.errors import CrmPermanentError, CrmTransientError

#: Statuses where retrying the identical request cannot succeed.
PERMANENT_STATUSES = frozenset({400, 401, 403, 404, 405, 422})
#: Statuses where it might.
TRANSIENT_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


def classify_response(response: httpx.Response) -> Exception | None:
    """Turn a non-2xx response into the right exception. None means success."""
    if response.is_success:
        return None

    detail = _describe(response)

    if response.status_code in PERMANENT_STATUSES:
        return CrmPermanentError(detail)

    if response.status_code == 429:
        return CrmTransientError(detail, retry_after_seconds=_retry_after(response))

    if response.status_code in TRANSIENT_STATUSES or response.status_code >= 500:
        return CrmTransientError(detail, retry_after_seconds=_retry_after(response))

    return CrmTransientError(detail)


def classify_exception(exc: Exception) -> Exception:
    """Turn a transport-level failure into a CRM error."""
    if isinstance(exc, httpx.TimeoutException):
        return CrmTransientError(f"HubSpot request timed out: {exc}")
    if isinstance(exc, httpx.TransportError):
        return CrmTransientError(f"Could not reach HubSpot: {exc}")
    return CrmTransientError(f"Unexpected HubSpot client error: {exc}")


def _retry_after(response: httpx.Response) -> int | None:
    """Respect the provider's own back-pressure signal when it sends one."""
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        # Clamp: a malicious or malformed header should not park an event for
        # a week.
        return max(1, min(int(float(raw)), 3600))
    except ValueError:
        return None


def _describe(response: httpx.Response) -> str:
    """A short, safe error string.

    Truncated, and it never includes request headers — the Authorization header
    carries the private app token, and error strings end up in the database and
    on the dashboard.
    """
    try:
        body = response.json()
        message = body.get("message") or body.get("error") or str(body)
    except Exception:
        message = response.text
    return f"HubSpot returned {response.status_code}: {str(message)[:500]}"
