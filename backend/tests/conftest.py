"""Shared pytest fixtures."""

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config.settings import Environment, Settings
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    """Explicit test settings, so the suite never depends on a .env file."""
    return Settings(
        environment=Environment.LOCAL,
        log_level="WARNING",
        frontend_origins="http://localhost:3000",
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    """A freshly composed application — this is why create_app is a factory."""
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """An HTTP client wired straight into the ASGI app.

    ASGITransport calls the application in-process: no socket, no port, no
    server. Fast, and it means the test suite needs nothing running.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
