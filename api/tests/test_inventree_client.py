"""Tests for the async InvenTree REST client."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from api.inventree import InvenTreeClient, InvenTreeClientError


def test_token_header_construction() -> None:
    client = InvenTreeClient(
        base_url="http://inventree.test",
        api_token="secret-token",
    )

    assert client._headers()["Authorization"] == "Token secret-token"
    assert client._headers()["Accept"] == "application/json"


@pytest.mark.asyncio
@respx.mock
async def test_pagination_handling() -> None:
    client = InvenTreeClient(
        base_url="http://inventree.test",
        api_token="secret-token",
    )
    respx.get("http://inventree.test/api/part/").mock(
        return_value=Response(
            200,
            json={
                "count": 2,
                "next": "http://inventree.test/api/part/?limit=1&offset=1",
                "previous": None,
                "results": [{"pk": 1, "name": "Part 1"}],
            },
        )
    )
    respx.get("http://inventree.test/api/part/?limit=1&offset=1").mock(
        return_value=Response(
            200,
            json={
                "count": 2,
                "next": None,
                "previous": "http://inventree.test/api/part/",
                "results": [{"pk": 2, "name": "Part 2"}],
            },
        )
    )

    records = await client.list_endpoint("/api/part/")

    assert records == [{"pk": 1, "name": "Part 1"}, {"pk": 2, "name": "Part 2"}]


@pytest.mark.asyncio
@respx.mock
async def test_client_error_does_not_leak_token() -> None:
    token = "super-secret-token"
    client = InvenTreeClient(
        base_url="http://inventree.test",
        api_token=token,
    )
    respx.get("http://inventree.test/api/part/").mock(
        return_value=Response(403, json={"detail": "forbidden"})
    )

    with pytest.raises(InvenTreeClientError) as exc_info:
        await client.list_endpoint("/api/part/")

    assert token not in str(exc_info.value)
    assert "403" in str(exc_info.value)

