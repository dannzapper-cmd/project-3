"""Tests for FastAPI endpoints."""

from __future__ import annotations

import pytest
import respx
from httpx import AsyncClient, Response


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
    assert "test-token" not in response.text


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

