"""Database engine and session factory.

The URL normalisation here is small and saves a lot of confusion. Railway,
Neon, Heroku and friends all hand you a `DATABASE_URL` in whichever form their
platform prefers:

    postgres://...            (Heroku-era, SQLAlchemy rejects it outright)
    postgresql://...          (valid, but picks psycopg2, which we do not install)
    postgresql+asyncpg://...  (a different driver entirely)

We normalise all of them to `postgresql+psycopg://`, so you can paste whatever
Railway gives you into the environment variable and it simply works. Getting
this wrong produces a startup crash that reads like a missing dependency.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.observability.logging import get_logger

_logger = get_logger(__name__)

_ASYNC_DRIVER = "postgresql+psycopg"


def normalise_database_url(url: str) -> str:
    """Coerce any PostgreSQL URL into the async driver this app uses.

    SQLite URLs pass through untouched: the test suite runs on
    `sqlite+aiosqlite://`, which is why the whole suite needs no database
    server. SQLite is never used in production.
    """
    if url.startswith("sqlite"):
        return url
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg2://", "postgresql://"):
        if url.startswith(prefix):
            return _ASYNC_DRIVER + "://" + url[len(prefix) :]
    if url.startswith("postgres://"):
        return _ASYNC_DRIVER + "://" + url[len("postgres://") :]
    return url


def sync_database_url(url: str) -> str:
    """The same URL for Alembic, which runs synchronously.

    psycopg 3 serves both modes from one package and one URL scheme, so this is
    a no-op for PostgreSQL — which is exactly why we chose psycopg over asyncpg.
    Kept as a named function so the intent is visible at the call site.
    """
    if url.startswith("sqlite+aiosqlite"):
        return url.replace("sqlite+aiosqlite", "sqlite", 1)
    return normalise_database_url(url)


def create_engine_from_url(
    url: str,
    *,
    echo: bool = False,
    pool_size: int = 5,
    max_overflow: int = 5,
) -> AsyncEngine:
    """Build the async engine.

    Connection pooling notes that matter in production:

    * `pool_pre_ping` costs one cheap round trip per checkout and eliminates the
      "server closed the connection unexpectedly" class of error entirely. Both
      Neon and Railway drop idle connections; this makes that invisible.
    * `pool_recycle` keeps connections younger than most proxy idle timeouts.
    * `prepare_threshold=None` disables psycopg's prepared-statement cache. This
      is REQUIRED when connecting through a transaction-mode pooler such as
      Neon's pgbouncer endpoint or PgBouncer generally; without it you get
      intermittent `prepared statement "_pg3_0" already exists` errors that look
      like a Postgres bug and are configuration.
    """
    if url.startswith("sqlite"):
        # SQLite (tests only) does not accept pool sizing arguments.
        return create_async_engine(url, echo=echo, future=True)

    return create_async_engine(
        url,
        echo=echo,
        future=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"prepare_threshold": None},
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Session factory used by the Unit of Work.

    `expire_on_commit=False` matters in an async application. With the default,
    every attribute access after a commit triggers a lazy refresh — which in
    async SQLAlchemy raises `MissingGreenlet` rather than quietly issuing a
    query. Turning it off means a committed object stays usable, which is what
    lets `capture_lead` return `lead.id` after the transaction closed.
    """
    return async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
    )


@asynccontextmanager
async def engine_lifespan(engine: AsyncEngine) -> AsyncIterator[AsyncEngine]:
    """Dispose of the pool on shutdown so connections are released cleanly."""
    try:
        yield engine
    finally:
        await engine.dispose()
        _logger.info("database_engine_disposed")
