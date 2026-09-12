"""Exception handlers — the one place errors become HTTP responses.

This is the translation layer for failures, and it mirrors the translation the
routers do for successes. The domain raises ``DomainError`` and has never heard
of status code 422; the application raises ``ApplicationError`` and has never
heard of 404. Mapping happens here, once, so that a rule can be reused by a
future CLI, worker or agent without dragging HTTP semantics along with it.

The last handler is the important one: any unhandled exception becomes a
generic 500 with no class name, no message and no traceback. The details go to
the log, tagged with the request id, where they belong.
"""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.application.errors import ApplicationError
from app.domain.shared.errors import DomainError
from app.observability.context import get_request_id
from app.observability.logging import get_logger
from app.schemas.errors import ErrorBody, ErrorDetail, ErrorResponse

_logger = get_logger(__name__)


def _render(
    *,
    status_code: int,
    code: str,
    message: str,
    details: list[ErrorDetail] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            details=details or [],
            request_id=get_request_id(),
        )
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


async def handle_domain_error(_request: Request, exc: Exception) -> JSONResponse:
    """A business rule said no. That is a client error, not a server fault."""
    assert isinstance(exc, DomainError)
    return _render(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code=exc.code,
        message=exc.message,
    )


async def handle_application_error(_request: Request, exc: Exception) -> JSONResponse:
    """A use case could not be carried out."""
    assert isinstance(exc, ApplicationError)
    return _render(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code=exc.code,
        message=exc.message,
    )


async def handle_request_validation_error(_request: Request, exc: Exception) -> JSONResponse:
    """Malformed input. Reshaped into our envelope instead of FastAPI's default.

    FastAPI's built-in 422 body is a bare ``{"detail": [...]}``, which is a
    different shape from every other error this API returns. One envelope means
    the frontend needs one error handler.
    """
    assert isinstance(exc, RequestValidationError)
    details = [
        ErrorDetail(
            field=".".join(str(part) for part in error["loc"][1:]) or None,
            message=str(error["msg"]),
        )
        for error in exc.errors()
    ]
    return _render(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="validation_error",
        message="Request validation failed.",
        details=details,
    )


async def handle_http_exception(_request: Request, exc: Exception) -> JSONResponse:
    """404s, 405s and any explicitly raised HTTPException."""
    assert isinstance(exc, StarletteHTTPException)
    detail: Any = exc.detail
    return _render(
        status_code=exc.status_code,
        code=f"http_{exc.status_code}",
        message=str(detail),
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """The catch-all. Log everything; return nothing.

    Leaking an exception message to a client is how internal table names, file
    paths and connection strings end up in someone's browser console.
    """
    _logger.exception(
        "unhandled_exception",
        method=request.method,
        path=request.url.path,
        exception_type=type(exc).__name__,
    )
    return _render(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="internal_error",
        message="An unexpected error occurred. Quote the request_id when reporting this.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach every handler above to the application."""
    app.add_exception_handler(DomainError, handle_domain_error)
    app.add_exception_handler(ApplicationError, handle_application_error)
    app.add_exception_handler(RequestValidationError, handle_request_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(Exception, handle_unexpected_error)
