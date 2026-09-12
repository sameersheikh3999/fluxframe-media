"""Shared pytest fixtures.

The integration and API tests run against **SQLite**, not PostgreSQL, and that
is a deliberate, narrow choice worth understanding:

* The whole suite runs on a laptop and in CI with no database server, no Docker
  and no credentials. A test suite you can only run with infrastructure attached
  is a test suite that stops being run.
* The ORM uses portable column types with PostgreSQL variants
  (`JSON().with_variant(JSONB, "postgresql")`, `sa.Uuid()`), so the same models
  drive both.
* No SQLite-specific SQL exists anywhere in the application.

What this does NOT cover, honestly: `FOR UPDATE SKIP LOCKED` (SQLite ignores row
locking), the partial index, and JSONB operators. Those are PostgreSQL-only
behaviours verified by rendering the migration (`alembic upgrade head --sql`)
and by running against a real database in staging. The trade is stated in
docs/testing.md rather than hidden.

Tables are created with `Base.metadata.create_all` rather than by running
migrations, because the migration targets PostgreSQL types.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api.rate_limit import reset_rate_limits
from app.config.settings import Environment, Settings
from app.infrastructure.database.base import Base
from app.infrastructure.database.engine import (
    create_engine_from_url,
    create_session_factory,
)
from app.main import create_app

TEST_INTERNAL_SECRET = "test-internal-secret"


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    """A throwaway SQLite database, one per test.

    A file rather than `:memory:` because an in-memory SQLite database is
    per-connection — a pool would hand out several, each seeing a different
    empty database, which produces baffling "no such table" failures.
    """
    return f"sqlite+aiosqlite:///{tmp_path.as_posix()}/test.db"


@pytest.fixture
def settings(database_url: str) -> Settings:
    """Explicit test settings, so the suite never depends on a .env file."""
    return Settings(
        environment=Environment.LOCAL,
        log_level="WARNING",
        frontend_origins="http://localhost:3000",
        database_url=database_url,
        internal_api_secret=TEST_INTERNAL_SECRET,
        # Driven manually in tests via the admin endpoint, so dispatch is
        # deterministic rather than racing a timer.
        outbox_dispatcher_enabled=False,
        rate_limit_enabled=False,
        enable_demo_generator=True,
    )


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    """An engine with the schema already created."""
    engine = create_engine_from_url(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)


@pytest.fixture
async def app(settings: Settings, engine: AsyncEngine) -> AsyncIterator[FastAPI]:
    """A fully composed application, schema already in place.

    Note that this goes through `create_app` and the real lifespan: the test
    exercises the actual wiring, including resource construction, rather than a
    hand-assembled approximation of it.
    """
    reset_rate_limits()
    application = create_app(settings)
    yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """An HTTP client wired straight into the ASGI app.

    `ASGITransport` calls the application in-process: no socket, no port, no
    server. Using the async context manager runs the lifespan, so background
    resources are created and disposed exactly as they are in production.
    """
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={"X-Internal-Secret": TEST_INTERNAL_SECRET},
        ) as http_client,
        # Entering the lifespan explicitly: httpx's ASGITransport does not, and
        # without it the database engine and HTTP client are never created.
        app.router.lifespan_context(app),
    ):
        yield http_client


@pytest.fixture
def valid_lead_payload() -> dict[str, object]:
    """A realistic HOT lead. 30 + 20 + 20 + 15 + 15 = 100."""
    return {
        "idempotency_key": "test-key-00000001",
        "first_name": "Sarah",
        "last_name": "Morgan",
        "email": "sarah.morgan@example.com",
        "phone": "+44 7700 900123",
        "company_name": "Bloom Skin Clinic",
        "website": "bloomskin.example.com",
        "industry": "beauty",
        "monthly_revenue": "100k_500k",
        "monthly_marketing_budget": "10k_plus",
        "content_volume": "30_plus",
        "primary_goal": "lead_generation",
        "start_timeline": "immediately",
        "message": "New clinic opening in six weeks and no content plan.",
        "attribution": {
            "utm_source": "google",
            "utm_medium": "cpc",
            "utm_campaign": "q3_clinics",
            "landing_page": "/book-call",
        },
    }
