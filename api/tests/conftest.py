"""Async test fixtures for the InvForge API."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.config import Settings
from api.main import create_app


@pytest_asyncio.fixture
async def test_client(tmp_path) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        inventree_base_url="http://inventree.test",
        inventree_api_token="test-token",
        data_dir=tmp_path / "data",
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            yield client

