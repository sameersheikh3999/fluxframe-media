"""Transport contracts for the health and readiness endpoints."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    """Response of GET /api/v1/health (liveness)."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok"] = "ok"
    service: str = Field(examples=["Fluxframe Media API"])
    version: str = Field(examples=["0.1.0"])
    environment: str = Field(examples=["local"])
    checked_at: datetime


class ReadinessCheckResponse(BaseModel):
    """The state of one dependency within a readiness response."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(examples=["database"])
    state: str = Field(
        description="ok | not_configured | failed",
        examples=["not_configured"],
    )
    detail: str | None = None


class ReadinessResponse(BaseModel):
    """Response of GET /api/v1/health/ready."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ready", "not_ready"]
    checks: list[ReadinessCheckResponse]
    checked_at: datetime
