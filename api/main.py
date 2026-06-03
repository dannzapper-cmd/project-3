"""FastAPI entrypoint for the InvForge AI Operations API."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from api.config import Settings
from api.ingestion import data_summary, ingest_inventree
from api.inventree import InvenTreeClient, InvenTreeClientError
from api.logging import configure_logging
from api.validation import DataValidationError, validate_processed_data
from observability.health import build_health_status

try:
    from observability import metrics as obs_metrics

    _METRICS_AVAILABLE = True
except ImportError:  # prometheus-client lives in the optional observability group
    obs_metrics = None  # type: ignore[assignment]
    _METRICS_AVAILABLE = False


def _build_inventree_client(settings: Settings) -> InvenTreeClient:
    return InvenTreeClient(
        base_url=settings.inventree_base_url,
        api_token=settings.inventree_api_token,
        username=settings.inventree_username,
        password=settings.inventree_password,
        timeout_seconds=settings.inventree_timeout_seconds,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    runtime_settings = settings or Settings.from_env()
    logger = structlog.get_logger(__name__)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = runtime_settings
        logger.info("api_startup")
        yield
        logger.info("api_shutdown")

    app = FastAPI(
        title="InvForge AI Operations API",
        version="0.2.0",
        lifespan=lifespan,
    )

    if _METRICS_AVAILABLE:
        obs_metrics.init_service_info()

        @app.middleware("http")
        async def _record_request_metrics(request: Request, call_next):
            start = time.perf_counter()
            try:
                response = await call_next(request)
            except Exception:
                obs_metrics.record_request(
                    request.method,
                    request.url.path,
                    500,
                    time.perf_counter() - start,
                )
                raise
            obs_metrics.record_request(
                request.method,
                request.url.path,
                response.status_code,
                time.perf_counter() - start,
            )
            return response

    @app.get("/health")
    async def health() -> JSONResponse:
        payload = build_health_status()
        status_code = 503 if payload["status"] == "unavailable" else 200
        return JSONResponse(content=payload, status_code=status_code)

    @app.get("/metrics")
    async def metrics() -> Response:
        if not _METRICS_AVAILABLE:
            return JSONResponse(
                content={
                    "status": "unavailable",
                    "detail": (
                        "Metrics require the optional observability dependency "
                        "group (prometheus-client)."
                    ),
                },
                status_code=503,
            )
        payload, content_type = obs_metrics.render_latest()
        return Response(content=payload, media_type=content_type)

    @app.get("/v1/inventory/status")
    async def inventory_status() -> dict[str, Any]:
        settings = app.state.settings
        summary = data_summary(settings.data_dir)
        return {
            "status": "ready",
            "inventree_base_url": settings.inventree_base_url,
            "inventree_token_configured": bool(
                settings.inventree_api_token
                and settings.inventree_api_token not in {"replace-me"}
            ),
            "inventree_basic_auth_configured": bool(
                settings.inventree_username
                and settings.inventree_password
                and settings.inventree_password
                not in {"replace-me", "replace-me-local-only"}
            ),
            "data_dir": str(settings.data_dir),
            "local_data": summary,
        }

    @app.post("/v1/ingest/inventree")
    async def ingest_inventory() -> dict[str, Any]:
        settings = app.state.settings
        try:
            client = _build_inventree_client(settings)
            result = await ingest_inventree(client=client, data_dir=settings.data_dir)
            validated = validate_processed_data(result.processed_dir)
        except ValueError as exc:
            logger.warning("ingestion_configuration_error", error=str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except InvenTreeClientError as exc:
            logger.warning("inventree_ingestion_failed", error=str(exc))
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except DataValidationError as exc:
            logger.warning("ingestion_validation_failed", error=str(exc))
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        logger.info("inventree_ingestion_completed", counts=result.raw_counts)
        return {
            "status": "completed",
            "raw_dir": str(result.raw_dir),
            "processed_dir": str(result.processed_dir),
            "counts": result.raw_counts,
            "validated_rows": validated,
        }

    @app.get("/v1/data/summary")
    async def local_data_summary() -> dict[str, Any]:
        settings = app.state.settings
        return data_summary(settings.data_dir)

    return app


app = create_app()
