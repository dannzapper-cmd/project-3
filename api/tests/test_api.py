"""Tests for FastAPI endpoints."""

from __future__ import annotations

import pytest
import respx
from httpx import ASGITransport, AsyncClient, Response

from api.config import Settings
from api.main import create_app


@pytest.mark.asyncio
async def test_health_endpoint(test_client: AsyncClient) -> None:
    response = await test_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "invforge-api"}


@pytest.mark.asyncio
async def test_inventory_status_does_not_expose_token(
    test_client: AsyncClient,
) -> None:
    response = await test_client.get("/v1/inventory/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["inventree_token_configured"] is True
    assert payload["inventree_basic_auth_configured"] is False
    assert "test-token" not in response.text


@pytest.mark.asyncio
async def test_ingest_endpoint_missing_credentials_fails_without_secret_leak(
    tmp_path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = Settings(
        inventree_base_url="http://inventree.test",
        inventree_api_token="replace-me",
        inventree_username="admin",
        inventree_password="replace-me-local-only",
        data_dir=tmp_path / "data",
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.post("/v1/ingest/inventree")

    assert response.status_code == 400
    assert "INVENTREE_API_TOKEN" in response.text
    assert "admin" not in response.text
    assert "replace-me-local-only" not in response.text
    assert "admin" not in caplog.text
    assert "replace-me-local-only" not in caplog.text


@pytest.mark.asyncio
@respx.mock
async def test_ingest_endpoint_with_mocked_inventree(
    test_client: AsyncClient,
) -> None:
    respx.get("http://inventree.test/api/part/").mock(
        return_value=Response(
            200,
            json=[
                {
                    "pk": 1,
                    "name": "Widget",
                    "description": "A test part",
                    "IPN": "W-001",
                    "category": 10,
                    "active": True,
                    "virtual": False,
                }
            ],
        )
    )
    respx.get("http://inventree.test/api/stock/").mock(
        return_value=Response(
            200,
            json=[
                {
                    "pk": 100,
                    "part": 1,
                    "quantity": 12.5,
                    "location": 5,
                    "status": "ok",
                    "batch": "B-1",
                }
            ],
        )
    )
    respx.get("http://inventree.test/api/part/category/").mock(
        return_value=Response(
            200,
            json=[
                {
                    "pk": 10,
                    "name": "Components",
                    "parent": None,
                    "description": "Part category",
                }
            ],
        )
    )
    respx.get("http://inventree.test/api/company/").mock(
        return_value=Response(
            200,
            json=[
                {
                    "pk": 50,
                    "name": "Supplier Co",
                    "is_supplier": True,
                    "is_manufacturer": False,
                    "is_customer": False,
                }
            ],
        )
    )

    response = await test_client.post("/v1/ingest/inventree")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["counts"] == {
        "parts": 1,
        "stock_records": 1,
        "categories": 1,
        "companies": 1,
    }
    assert payload["validated_rows"]["stock_records.csv"] == 1


@pytest.mark.asyncio
@respx.mock
async def test_ingest_endpoint_error_does_not_leak_token(
    test_client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    respx.get("http://inventree.test/api/part/").mock(
        return_value=Response(500, json={"detail": "boom"})
    )

    response = await test_client.post("/v1/ingest/inventree")

    assert response.status_code == 502
    assert "test-token" not in response.text
    assert "test-token" not in caplog.text

