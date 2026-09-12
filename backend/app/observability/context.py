"""Per-request context, carried without threading it through every signature.

A ``ContextVar`` is the asyncio-safe equivalent of thread-local storage: each
task sees its own value, so two requests handled concurrently never read each
other's request id.

The request id set here is the thread that will eventually stitch together:
    the HTTP access log line
    -> every application log emitted while handling that request
    -> the correlation_id stamped on outbox events (Phase 3)
    -> the ai_runs row for an LLM call made on that lead's behalf (Phase 6)

Being able to grep one id across all of those is most of what "observability"
means in a system this size.
"""

from contextvars import ContextVar, Token

_REQUEST_ID: ContextVar[str | None] = ContextVar("fluxframe_request_id", default=None)


def set_request_id(request_id: str) -> Token[str | None]:
    """Bind a request id to the current context. Returns a reset token."""
    return _REQUEST_ID.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    """Restore whatever request id was bound before ``set_request_id``."""
    _REQUEST_ID.reset(token)


def get_request_id() -> str | None:
    """The request id for the current context, if one is bound."""
    return _REQUEST_ID.get()
