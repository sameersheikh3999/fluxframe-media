"""Errors raised by use cases, as opposed to by business rules.

The distinction is worth holding on to:

    DomainError       a business rule said no
                      ("a lead cannot move from WON back to NEW")

    ApplicationError  the use case could not be carried out
                      ("no lead exists with that id", "this key was reused")

Both are expected, both are the caller's problem, and both are mapped to HTTP
status codes in exactly one place: app/api/errors.py. Nothing in this file
imports FastAPI or knows what a 404 is.
"""


class ApplicationError(Exception):
    """Base class for use-case failures."""

    code: str = "application_error"
    #: Advisory HTTP status for the API layer. Kept here rather than in a
    #: lookup table in app/api/ so that adding an error type does not require
    #: editing a second file — but note the direction: this is a *hint* the
    #: adapter chooses to honour, and nothing in this layer performs HTTP.
    status_hint: int = 422

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class LeadNotFoundError(ApplicationError):
    code = "lead_not_found"
    status_hint = 404


class IdempotencyConflictError(ApplicationError):
    """The same idempotency key arrived with a different payload.

    A genuine retry sends identical data and is answered with the original
    result. Different data under the same key means the client is buggy, and
    silently overwriting or silently ignoring would both hide it.
    """

    code = "idempotency_conflict"
    status_hint = 409


class DemoGeneratorDisabledError(ApplicationError):
    code = "demo_generator_disabled"
    status_hint = 403


class DemoBatchTooLargeError(ApplicationError):
    code = "demo_batch_too_large"
    status_hint = 422


class AiUnavailableError(ApplicationError):
    """The AI provider is not configured or could not be reached."""

    code = "ai_unavailable"
    status_hint = 503


class AiResponseError(ApplicationError):
    """The model replied, but not with something we can use."""

    code = "ai_invalid_response"
    status_hint = 502


class CrmError(ApplicationError):
    """Base for CRM failures. Subclasses drive the retry policy."""

    code = "crm_error"
    status_hint = 502


class CrmTransientError(CrmError):
    """Worth retrying: 429, 5xx, timeout, connection reset."""

    code = "crm_transient_error"

    def __init__(self, message: str, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        #: Honour the provider's own Retry-After when it sends one. Guessing
        #: faster than the provider asked is how you earn a longer rate limit.
        self.retry_after_seconds = retry_after_seconds


class CrmPermanentError(CrmError):
    """Never worth retrying: 400, 401, 403, malformed property.

    Retrying these forever is worse than failing: it hides a configuration bug
    behind an endlessly "pending" queue.
    """

    code = "crm_permanent_error"


class CrmNotConfiguredError(CrmError):
    """No CRM credential is present. A normal state, not a fault."""

    code = "crm_not_configured"
