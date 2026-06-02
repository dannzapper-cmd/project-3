"""Tests for the async InvenTree REST client."""

from __future__ import annotations

import base64

import pytest
import respx
from httpx import Response

from api.inventree import InvenTreeClient, InvenTreeClientError


def test_token_header_construction() -> None:
    client = InvenTreeClient(
        base_url="http://inventree.test",
        api_token="secret-token",
        username="admin",
        password="local-password",
    )

    assert client.auth_mode == "token"
    assert client._auth() is None
    assert client._headers()["Authorization"] == "Token secret-token"
    assert client._headers()["Accept"] == "application/json"


@pytest.mark.asyncio
@respx.mock
async def test_basic_auth_fallback_when_token_missing() -> None:
    password = "local-password"
    client = InvenTreeClient(
        base_url="http://inventree.test",
        api_token="replace-me",
        username="admin",
        password=password,
    )
    route = respx.get("http://inventree.test/api/part/").mock(
        return_value=Response(200, json=[])
    )

    records = await client.list_endpoint("/api/part/")

    encoded = base64.b64encode(b"admin:local-password").decode()
    assert records == []
    assert client.auth_mode == "basic"
    assert route.calls.last.request.headers["Authorization"] == f"Basic {encoded}"


def test_missing_credentials_fails_clearly() -> None:
    with pytest.raises(ValueError) as exc_info:
        InvenTreeClient(
            base_url="http://inventree.test",
            api_token="replace-me",
            username="admin",
            password="replace-me-local-only",
        )

    message = str(exc_info.value)
    assert "INVENTREE_API_TOKEN" in message
    assert "INVENTREE_USERNAME" in message
    assert "INVENTREE_PASSWORD" in message
    assert "admin" not in message
    assert "replace-me-local-only" not in message


@pytest.mark.asyncio
@respx.mock
async def test_pagination_handling() -> None:
    client = InvenTreeClient(
        base_url="http://inventree.test",
        api_token="secret-token",
    )
    respx.get("http://inventree.test/api/part/").mock(
        side_effect=[
            Response(
                200,
                json={
                    "count": 2,
                    "next": "http://inventree.test/api/part/?limit=1&offset=1",
                    "previous": None,
                    "results": [{"pk": 1, "name": "Part 1"}],
                },
            ),
            Response(
                200,
                json={
                    "count": 2,
                    "next": None,
                    "previous": "http://inventree.test/api/part/",
                    "results": [{"pk": 2, "name": "Part 2"}],
                },
            ),
        ]
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



@pytest.mark.asyncio
@respx.mock
async def test_basic_auth_error_does_not_leak_credentials() -> None:
    username = "admin"
    password = "very-secret-local-password"
    client = InvenTreeClient(
        base_url="http://inventree.test",
        api_token=None,
        username=username,
        password=password,
    )
    respx.get("http://inventree.test/api/part/").mock(
        return_value=Response(401, json={"detail": "invalid credentials"})
    )

    with pytest.raises(InvenTreeClientError) as exc_info:
        await client.list_endpoint("/api/part/")

    message = str(exc_info.value)
    assert username not in message
    assert password not in message
    assert "401" in message
