"""The single error envelope every failing endpoint returns.

One shape for every failure means the frontend writes one error handler instead
of one per endpoint, and a new endpoint cannot invent a new error format by
accident.

    {
      "error": {
        "code": "validation_error",
        "message": "Request validation failed.",
        "details": [{"field": "email", "message": "value is not a valid email"}],
        "request_id": "8f14e45fceea167a"
      }
    }

`code` is stable and machine-readable — branch on it. `message` is for humans
and may change. Stack traces and exception class names never appear here.
"""

from pydantic import BaseModel, ConfigDict, Field


class ErrorDetail(BaseModel):
    """One specific thing that was wrong, usually a field-level problem."""

    model_config = ConfigDict(frozen=True)

    field: str | None = Field(
        default=None,
        description="Dotted path to the offending input field, when applicable.",
        examples=["email"],
    )
    message: str = Field(description="What was wrong with it.")


class ErrorBody(BaseModel):
    """The contents of the error envelope."""

    model_config = ConfigDict(frozen=True)

    code: str = Field(
        description="Stable, machine-readable error identifier. Branch on this.",
        examples=["validation_error"],
    )
    message: str = Field(description="Human-readable summary. Do not branch on this.")
    details: list[ErrorDetail] = Field(default_factory=list)
    request_id: str | None = Field(
        default=None,
        description="Correlates this response with the server logs.",
    )


class ErrorResponse(BaseModel):
    """The response body returned by every 4xx and 5xx."""

    model_config = ConfigDict(frozen=True)

    error: ErrorBody
