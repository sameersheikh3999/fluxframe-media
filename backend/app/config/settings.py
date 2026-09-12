"""Application settings.

Two principles at work here.

1. **Fail at startup, never at request time.** `get_settings()` is called during
   application construction. A missing or malformed variable crashes the process
   on boot, where you will notice it, rather than 503-ing one unlucky request
   three days later.

2. **Settings are injected, not imported.** Only `app.main`, `app.dependencies`
   and infrastructure adapters read this module. Services receive the values
   they need as constructor arguments, which is why `LeadService` can be
   instantiated in a test with no environment at all.

Every optional integration (database, CRM, AI) degrades to a documented,
supported mode when its credential is absent. That is what makes a first Railway
deploy possible with nothing but `DATABASE_URL` set.
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
    app_version: str = "1.0.0"
    environment: Environment = Environment.LOCAL
    api_v1_prefix: str = "/api/v1"

    # --- logging ------------------------------------------------------------
    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"

    # --- database -----------------------------------------------------------
    #: Paste whatever Railway or Neon gives you. The engine normalises
    #: postgres://, postgresql:// and postgresql+asyncpg:// to the psycopg
    #: async driver, so all three work unchanged.
    #: Empty is allowed: the app boots, serves the marketing site and reports
    #: the database as not configured. Lead capture returns 503 until set.
    database_url: str = ""
    #: Alembic's connection. On Neon this should be the DIRECT (unpooled)
    #: endpoint — migrations through a transaction-mode pooler misbehave.
    #: Falls back to database_url, which is correct for Railway.
    database_migration_url: str = ""
    database_echo: bool = False
    database_pool_size: int = 5
    database_max_overflow: int = 5

    # --- CORS ---------------------------------------------------------------
    # Comma-separated, kept as a string rather than a list: pydantic-settings
    # tries to JSON-decode complex types read from the environment, which turns
    # a perfectly reasonable "a,b" into a confusing parse error.
    frontend_origins: str = "http://localhost:3000"
    #: Vercel gives every preview deployment a unique hostname, so previews
    #: cannot be listed exhaustively. A regex is the narrowest tool that works.
    frontend_origin_regex: str | None = None

    # --- internal access ----------------------------------------------------
    #: Shared secret guarding /dashboard and /demo endpoints. Held only by the
    #: Next.js server, never by the browser. Empty in local development leaves
    #: those endpoints open, which is convenient locally and refused in
    #: production by the validator below.
    internal_api_secret: str = ""

    # --- HubSpot ------------------------------------------------------------
    hubspot_access_token: str = ""
    hubspot_base_url: str = "https://api.hubapi.com"
    hubspot_timeout_seconds: float = 10.0
    #: Default off: ten synthetic contacts per click would pollute a real
    #: HubSpot portal you may want to show a client.
    hubspot_sync_demo_leads: bool = False

    # --- AI -----------------------------------------------------------------
    anthropic_api_key: str = ""
    ai_model: str = "claude-sonnet-5"
    ai_max_tokens: int = 1024
    ai_timeout_seconds: float = 45.0

    # --- demo generator -----------------------------------------------------
    enable_demo_generator: bool = True
    demo_max_batch_size: int = 10

    # --- outbox dispatcher --------------------------------------------------
    outbox_dispatcher_enabled: bool = True
    outbox_poll_interval_seconds: float = 5.0
    outbox_batch_size: int = 20
    outbox_max_attempts: int = 6
    outbox_stalled_after_seconds: int = 300

    # --- rate limiting ------------------------------------------------------
    #: Applies to the public lead endpoint only. In-process and per-instance:
    #: with two Railway replicas the effective limit doubles. That is an
    #: accepted trade — a shared limiter would mean adding Redis, which is a
    #: lot of infrastructure to buy precision a portfolio site does not need.
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 10
    rate_limit_window_seconds: int = 60

    # --- derived ------------------------------------------------------------

    @property
    def cors_origins(self) -> list[str]:
        """`frontend_origins` split into the list Starlette's CORS wants."""
        return [o.strip() for o in self.frontend_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION

    @property
    def log_as_json(self) -> bool:
        return self.log_format == "json"

    @property
    def has_database(self) -> bool:
        return bool(self.database_url.strip())

    @property
    def has_crm(self) -> bool:
        return bool(self.hubspot_access_token.strip())

    @property
    def has_ai(self) -> bool:
        return bool(self.anthropic_api_key.strip())

    @property
    def effective_migration_url(self) -> str:
        return self.database_migration_url.strip() or self.database_url.strip()

    # --- validation ---------------------------------------------------------

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        upper = value.upper()
        if upper not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}, got {value!r}")
        return upper

    @model_validator(mode="after")
    def _validate_production_safety(self) -> "Settings":
        """Refuse to boot in a configuration that is unsafe in production.

        Crashing is the correct response to each of these. A running service
        with `allow_origins=["*"]` looks perfectly healthy while letting any
        site on the internet call your API; an unprotected demo generator on a
        public URL is an open write endpoint.
        """
        if not self.is_production:
            return self

        problems: list[str] = []
        if "*" in self.cors_origins:
            problems.append(
                "FRONTEND_ORIGINS must list explicit origins in production; '*' is not allowed."
            )
        if not self.internal_api_secret.strip():
            problems.append(
                "INTERNAL_API_SECRET must be set in production: it is what "
                "protects the dashboard and demo endpoints."
            )
        if problems:
            raise ValueError(" ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    """The process-wide settings singleton.

    Cached because reading and validating the environment on every request
    would be pointless work — and because FastAPI's `Depends(get_settings)`
    then hands every caller the same instance.
    """
    return Settings()
