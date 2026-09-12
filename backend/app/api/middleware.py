"""Request-scoped context and access logging.

Every request gets an id. If the caller supplied ``X-Request-ID`` we keep it —
so a trace can be followed across the Next.js server and this backend — and
otherwise we mint one. It is bound into the logging context for the lifetime of
the request and echoed back in the response header, which means a user can send
you a failing request id and you can find the exact log line.

From Phase 3, this same id is stamped onto outbox events as `correlation_id`,
so "which web request caused this HubSpot call?" becomes a one-line query.
"""

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.observability.context import reset_request_id, set_request_id
from app.observability.logging import get_logger

REQUEST_ID_HEADER = "X-Request-ID"

_logger = get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Binds a request id, times the request and logs one structured line."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        token = set_request_id(request_id)
        structlog.contextvars.bind_contextvars(request_id=request_id)

        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            _logger.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_ms=duration_ms,
            )
            structlog.contextvars.clear_contextvars()
            reset_request_id(token)
