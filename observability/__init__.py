"""InvForge PR-07 observability layer.

Lightweight, local/dev-only observability for the AI Operations Layer:
health status, Prometheus metrics, and structured logging. Reads only small,
safe summary fields from existing PR-04/PR-05 artifacts (existence, mtime, and
allowlisted scalar fields). Never exposes raw artifact payloads, file paths,
secrets, or high-cardinality values.
"""

from observability.artifacts import (
    ARTIFACT_KEYS,
    ArtifactSpec,
    default_artifact_specs,
)
from observability.health import build_health_status

__all__ = [
    "ARTIFACT_KEYS",
    "ArtifactSpec",
    "build_health_status",
    "default_artifact_specs",
]
