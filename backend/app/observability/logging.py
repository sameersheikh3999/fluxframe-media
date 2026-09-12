"""Structured logging configuration.

Two renderers, one pipeline:

    LOG_FORMAT=console   human-readable, coloured, for your terminal
    LOG_FORMAT=json      one JSON object per line, for Railway's log search

The important word is *structured*. ``log.info("lead_captured", lead_id=...,
temperature="HOT")`` produces queryable fields, where an f-string produces prose
you have to write a regex against later.

Uvicorn's own logs are routed through the same pipeline via ProcessorFormatter,
so a production log stream is uniformly JSON rather than half JSON and half
Uvicorn's default format.
"""

import logging
import logging.config
from collections.abc import Callable
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from app.observability.context import get_request_id


def _add_request_id(_logger: object, _method_name: str, event_dict: EventDict) -> EventDict:
    """Stamp the current request id onto every log line, if one is bound."""
    request_id = get_request_id()
    if request_id is not None:
        event_dict["request_id"] = request_id
    return event_dict


def configure_logging(*, level: str = "INFO", json_output: bool = False) -> None:
    """Configure structlog and the standard library to share one pipeline.

    Safe to call more than once; the test suite relies on that.
    """
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    # Processors applied to events from structlog loggers (our code).
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        _add_request_id,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            # Hands the event off to the stdlib handler configured below.
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=not json_output)
    )

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "structured": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processor": renderer,
                    # Applied to records from libraries that use plain logging
                    # (uvicorn, asyncio) so they gain the same fields as ours.
                    "foreign_pre_chain": shared_processors,
                },
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "structured",
                },
            },
            "root": {"handlers": ["default"], "level": level.upper()},
            "loggers": {
                # Uvicorn's access log duplicates our own request middleware
                # log line, with less information. Silence it, keep ours.
                "uvicorn.access": {
                    "handlers": ["default"],
                    "level": "WARNING",
                    "propagate": False,
                },
                "uvicorn.error": {
                    "handlers": ["default"],
                    "level": level.upper(),
                    "propagate": False,
                },
            },
        }
    )


def get_logger(name: str) -> Any:
    """Return a bound structlog logger.

    The return type is intentionally loose: structlog's stub for
    ``get_logger`` is dynamic, and pinning it here would buy false precision.
    """
    factory: Callable[..., Any] = structlog.stdlib.get_logger
    return factory(name)
