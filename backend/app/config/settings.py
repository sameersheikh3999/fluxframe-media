"""Application settings.

Two principles at work here.

1. Fail at startup, never at request time.
   ``get_settings()`` is called during application construction. A missing or
   malformed variable crashes the process on boot, where you will notice it,
   rather than 503-ing one unlucky request three days later.

2. Settings are injected, not imported.
   Only app.main and app.dependencies read this module. Services receive the
   values they need as constructor arguments. That is why SystemService can be
   instantiated in a test without an environment file existing.
"""

from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Where this process is running."""

    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Every environment variable the backend reads, in one validated object."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    # --- identity -----------------------------------------------------------
    app_name: str = "Fluxframe Media API"
    app_version: str = "0.1.0"
    environment: Environment = Environment.LOCAL
    api_v1_prefix: str = "/api/v1"

    # --- logging ------------------------------------------------------------
    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"

    # --- CORS ---------------------------------------------------------------
    # Comma-separated, kept as a string rather than a list: pydantic-settings
    # tries to JSON-decode complex types read from the environment, which turns
    # a perfectly reasonable "a,b" into a confusing parse error. Splitting it
    # ourselves in `cors_origins` is duller and never surprises anyone.
    frontend_origins: str = "http://localhost:3000"
    # Vercel gives every preview deployment a unique hostname, so previews
    # cannot be listed exhaustively. A regex is the narrowest tool that works.
    # "*" is never acceptable — see the validator below.
    frontend_origin_regex: str | None = None

    @property
    def cors_origins(self) -> list[str]:
        """`frontend_origins` split into the list Starlette's CORS wants."""
        return [origin.strip() for origin in self.frontend_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION

    @property
    def log_as_json(self) -> bool:
        return self.log_format == "json"

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        upper = value.upper()
        if upper not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}, got {value!r}")
        return upper

    @model_validator(mode="after")
    def _reject_wildcard_cors_in_production(self) -> "Settings":
        """A wildcard CORS origin in production is a configuration bug.

        Refusing to boot is the correct response. A running service with
        `allow_origins=["*"]` looks perfectly healthy while letting any site on
        the internet call your API with the visitor's credentials attached.
        """
        if self.is_production and "*" in self.cors_origins:
            raise ValueError(
                "FRONTEND_ORIGINS must list explicit origins in production; '*' is not allowed."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """The process-wide settings singleton.

    Cached because reading and validating the environment on every request
    would be pointless work — and because FastAPI's ``Depends(get_settings)``
    then hands every caller the same instance.
    """
    return Settings()
