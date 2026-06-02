"""Read-only async InvenTree REST client."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class InvenTreeClientError(RuntimeError):
    """Safe error for InvenTree API failures.

    The message intentionally omits request headers and tokens.
    """

    def __init__(
        self,
        message: str,
        *,
        url: str | None = None,
        status_code: int | None = None,
    ) -> None:
        self.url = url
        self.status_code = status_code
        details = message
        if status_code is not None:
            details = f"{details} (status_code={status_code})"
        if url:
            details = f"{details} url={url}"
        super().__init__(details)


@dataclass(frozen=True)
class ResourceSnapshot:
    """Records returned from one InvenTree endpoint."""

    name: str
    endpoint: str
    records: list[dict[str, Any]]


class InvenTreeClient:
    """Small read-only client for documented InvenTree API endpoints."""

    INVENTORY_RESOURCES: dict[str, str] = {
        # Confirmed in InvenTree REST API schema docs for v1.3.x.
        "parts": "/api/part/",
        "stock_records": "/api/stock/",
        "categories": "/api/part/category/",
        "companies": "/api/company/",
    }

    def __init__(
        self,
        *,
        base_url: str,
        api_token: str,
        timeout_seconds: float = 10.0,
        max_pages: int = 100,
    ) -> None:
        if not base_url:
            raise ValueError("InvenTree base URL is required")
        if not api_token or api_token == "replace-me":
            raise ValueError("INVENTREE_API_TOKEN must be configured")
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.timeout = httpx.Timeout(timeout_seconds)
        self.max_pages = max_pages

    def _headers(self) -> dict[str, str]:
        """Build token auth headers for InvenTree without logging the token."""

        return {
            "Accept": "application/json",
            "Authorization": f"Token {self.api_token}",
        }

    async def _get_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        try:
            response = await client.get(url, params=params)
        except httpx.TimeoutException as exc:
            raise InvenTreeClientError(
                "Timed out while calling InvenTree API",
                url=url,
            ) from exc
        except httpx.RequestError as exc:
            raise InvenTreeClientError(
                "Could not reach InvenTree API",
                url=url,
            ) from exc

        if response.status_code >= 400:
            raise InvenTreeClientError(
                "InvenTree API returned an error",
                url=url,
                status_code=response.status_code,
            )

        try:
            return response.json()
        except ValueError as exc:
            raise InvenTreeClientError(
                "InvenTree API returned non-JSON response",
                url=url,
                status_code=response.status_code,
            ) from exc

    async def list_endpoint(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return all records from an endpoint, following DRF pagination."""

        records: list[dict[str, Any]] = []
        next_url: str | None = endpoint
        current_params = params
        pages = 0

        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=self.timeout,
        ) as client:
            while next_url:
                pages += 1
                if pages > self.max_pages:
                    raise InvenTreeClientError(
                        "InvenTree pagination exceeded configured page limit",
                        url=next_url,
                    )

                payload = await self._get_json(
                    client,
                    next_url,
                    params=current_params,
                )
                current_params = None

                if isinstance(payload, list):
                    page_records = payload
                    next_url = None
                elif isinstance(payload, dict) and isinstance(
                    payload.get("results"), list
                ):
                    page_records = payload["results"]
                    next_url = payload.get("next")
                else:
                    raise InvenTreeClientError(
                        "InvenTree API response did not match list pagination format",
                        url=next_url,
                    )

                records.extend(
                    record for record in page_records if isinstance(record, dict)
                )

        return records

    async def fetch_inventory_snapshots(self) -> list[ResourceSnapshot]:
        """Fetch PR-02 inventory resources using documented read endpoints."""

        snapshots: list[ResourceSnapshot] = []
        for name, endpoint in self.INVENTORY_RESOURCES.items():
            records = await self.list_endpoint(endpoint)
            snapshots.append(
                ResourceSnapshot(name=name, endpoint=endpoint, records=records)
            )
        return snapshots

