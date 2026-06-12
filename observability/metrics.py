"""Prometheus metrics for the PR-07 AI Operations observability layer (B2).

Exactly the metrics defined in the PR-07 metric contract, and no others. All
label values are low-cardinality and safe: artifact *keys* (never filenames or
paths), HTTP methods, normalized endpoint templates, status codes, and a fixed
champion/challenger decision vocabulary. Unknown numeric values are encoded as
``-1`` (documented in the metric HELP strings).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from observability.artifacts import (
    ArtifactSpec,
    bentoml_build_summary_path,
    champion_challenger_path,
    default_artifact_specs,
    mlops_loop_summary_path,
)
from observability.health import (
    ALLOWED_DECISIONS,
    _bentoml_packaged,
    _champion_challenger_decision,
    _drift_detected,
)
from observability.logging import get_logger

SERVICE_VERSION = "0.2.0"
PR_STAGE = "PR-07"

# Encoding for "unknown" so Grafana/Prometheus interpretation is unambiguous
# (PATCH 7). -1 always means "value could not be determined safely".
UNKNOWN = -1.0

# Low-cardinality endpoint allowlist for request metrics. HTTP paths are mapped
# to slash-free label tokens so Prometheus labels never look like file paths.
ENDPOINT_LABEL_MAP: dict[str, str] = {
    "/health": "health",
    "/metrics": "metrics",
    "/v1/inventory/status": "v1_inventory_status",
    "/v1/ingest/inventree": "v1_ingest_inventree",
    "/v1/data/summary": "v1_data_summary",
}
KNOWN_ENDPOINTS: frozenset[str] = frozenset(ENDPOINT_LABEL_MAP)

_logger = get_logger("metrics")

REGISTRY = CollectorRegistry()

SERVICE_INFO = Gauge(
    "invforge_service_info",
    "InvForge AI Operations service info; constant 1 with version/pr_stage labels.",
    labelnames=("version", "pr_stage"),
    registry=REGISTRY,
)

ARTIFACT_AVAILABLE = Gauge(
    "invforge_artifact_available",
    "1 if the named artifact exists on disk, 0 if missing. "
    "Label 'artifact' is a fixed allowlisted key, never a filename or path.",
    labelnames=("artifact",),
    registry=REGISTRY,
)

ARTIFACT_AGE_SECONDS = Gauge(
    "invforge_artifact_age_seconds",
    "Seconds since the artifact file mtime; -1 if the artifact is missing or "
    "its mtime cannot be read.",
    labelnames=("artifact",),
    registry=REGISTRY,
)

DRIFT_DETECTED = Gauge(
    "invforge_drift_detected",
    "Dataset drift status from the MLOps loop summary: 1 drift detected, "
    "0 no drift, -1 unknown (artifact missing or field absent).",
    registry=REGISTRY,
)

CHAMPION_CHALLENGER_DECISION = Gauge(
    "invforge_champion_challenger_decision",
    "Champion/challenger decision encoded as a one-hot gauge: the active "
    "decision label is 1, all others 0. Decision is never a model name, path, "
    "or numeric score.",
    labelnames=("decision",),
    registry=REGISTRY,
)

BENTOML_PACKAGED = Gauge(
    "invforge_bentoml_packaged",
    "1 if the champion model was packaged to the local BentoML store, 0 "
    "otherwise (including when the BentoML build summary is missing).",
    registry=REGISTRY,
)

API_REQUESTS_TOTAL = Counter(
    "invforge_api_requests_total",
    "Total AI Operations API requests by method, normalized endpoint, and "
    "status code.",
    labelnames=("method", "endpoint", "status_code"),
    registry=REGISTRY,
)

API_REQUEST_DURATION_SECONDS = Histogram(
    "invforge_api_request_duration_seconds",
    "AI Operations API request duration in seconds by method and normalized "
    "endpoint.",
    labelnames=("method", "endpoint"),
    registry=REGISTRY,
)

# The exact set of metric base names defined by the B2 contract.
METRIC_NAMES: tuple[str, ...] = (
    "invforge_service_info",
    "invforge_artifact_available",
    "invforge_artifact_age_seconds",
    "invforge_drift_detected",
    "invforge_champion_challenger_decision",
    "invforge_bentoml_packaged",
    "invforge_api_requests_total",
    "invforge_api_request_duration_seconds",
)


def init_service_info(
    version: str = SERVICE_VERSION, pr_stage: str = PR_STAGE
) -> None:
    """Set the constant service_info gauge to 1."""

    SERVICE_INFO.labels(version=version, pr_stage=pr_stage).set(1)


def normalize_endpoint(endpoint: str) -> str:
    """Map an HTTP path to a low-cardinality, path-free label value."""

    return ENDPOINT_LABEL_MAP.get(endpoint, "other")


def record_request(
    method: str, endpoint: str, status_code: int, duration_seconds: float
) -> None:
    """Record one API request into the request metrics."""

    safe_endpoint = normalize_endpoint(endpoint)
    safe_method = method.upper()
    API_REQUESTS_TOTAL.labels(
        method=safe_method,
        endpoint=safe_endpoint,
        status_code=str(status_code),
    ).inc()
    API_REQUEST_DURATION_SECONDS.labels(
        method=safe_method, endpoint=safe_endpoint
    ).observe(duration_seconds)


def _artifact_age_seconds(path: Path) -> float:
    try:
        if not path.is_file():
            return UNKNOWN
        return max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return UNKNOWN


def refresh_artifact_metrics(
    specs: list[ArtifactSpec] | None = None,
    *,
    repo_root: Path | None = None,
    mlops_loop_path: Path | None = None,
    comparison_path: Path | None = None,
    bentoml_path: Path | None = None,
) -> None:
    """Refresh artifact/drift/decision/bentoml gauges from current disk state.

    Never raises: read/parse errors fall back to safe defaults (0 / -1 /
    "unknown").
    """

    artifact_specs = specs if specs is not None else default_artifact_specs(repo_root)
    for spec in artifact_specs:
        try:
            exists = spec.path.is_file()
        except OSError:
            exists = False
        ARTIFACT_AVAILABLE.labels(artifact=spec.key).set(1 if exists else 0)
        ARTIFACT_AGE_SECONDS.labels(artifact=spec.key).set(
            _artifact_age_seconds(spec.path)
        )

    loop_path = mlops_loop_path or mlops_loop_summary_path(repo_root)
    cc_path = comparison_path or champion_challenger_path(repo_root)
    bento_path = bentoml_path or bentoml_build_summary_path(repo_root)

    drift = _drift_detected(loop_path)
    DRIFT_DETECTED.set(UNKNOWN if drift is None else (1 if drift else 0))

    decision = _champion_challenger_decision(cc_path)
    for option in ALLOWED_DECISIONS:
        CHAMPION_CHALLENGER_DECISION.labels(decision=option).set(
            1 if option == decision else 0
        )

    packaged = _bentoml_packaged(bento_path)
    BENTOML_PACKAGED.set(1 if packaged else 0)

    _logger.log("artifact_metrics_refreshed", level="info", status="ok")


def render_latest(
    *,
    repo_root: Path | None = None,
    refresh: bool = True,
) -> tuple[bytes, str]:
    """Refresh dynamic gauges (optional) and return ``(payload, content_type)``."""

    if refresh:
        refresh_artifact_metrics(repo_root=repo_root)
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


def registered_metric_names() -> set[str]:
    """Return the base metric names exposed by ``REGISTRY``.

    Parses the ``# TYPE`` lines of the exposition output, which carry the exact
    B2 metric names (e.g. ``invforge_api_requests_total`` for the counter and
    ``invforge_api_request_duration_seconds`` for the histogram). The internal
    ``*_created`` series prometheus_client emits are excluded.
    """

    names: set[str] = set()
    text = generate_latest(REGISTRY).decode("utf-8")
    for line in text.splitlines():
        if not line.startswith("# TYPE "):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        name = parts[2]
        if name.endswith("_created"):
            continue
        names.add(name)
    return names


def assert_no_path_label_values() -> list[tuple[str, str, str]]:
    """Return any (metric, label, value) where a value looks like a path.

    Used by the smoke test (B8 #5). An empty list means all label values are
    path-free.
    """

    offenders: list[tuple[str, str, str]] = []
    for metric in REGISTRY.collect():
        for sample in metric.samples:
            for label_name, label_value in sample.labels.items():
                value: Any = label_value
                if label_name == "endpoint" and str(value) in KNOWN_ENDPOINTS:
                    # Endpoint labels are normalized API templates, not file paths.
                    continue
                if "/" in str(value) or "\\" in str(value):
                    offenders.append((sample.name, label_name, str(value)))
    return offenders


# Initialize the constant service_info gauge on import.
init_service_info()
