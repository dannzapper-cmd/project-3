"""Strict, fast, offline smoke test for PR-07 observability (B8).

Runs in well under 10 seconds and requires no Docker, no running server, and no
browser. Exits 0 on success, 1 on any exception, missing key, or unsafe label.
"""

from __future__ import annotations

import sys
from pathlib import Path

REQUIRED_HEALTH_KEYS = {
    "status",
    "pr_stage",
    "artifacts",
    "drift_detected",
    "bentoml_packaged",
    "champion_challenger_decision",
}
REQUIRED_ARTIFACT_KEYS = {
    "decision_summary",
    "decision_recommendations",
    "mlops_loop_summary",
    "registry_summary",
    "champion_challenger_comparison",
}


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_smoke() -> None:
    from observability import health as health_mod
    from observability import metrics as metrics_mod
    from observability.artifacts import ArtifactSpec

    # 1. Modules import and key entry points are callable.
    _check(callable(health_mod.build_health_status), "health builder not callable")
    _check(callable(metrics_mod.render_latest), "metrics render not callable")
    _check(
        callable(metrics_mod.refresh_artifact_metrics),
        "metrics refresh not callable",
    )

    # 2. Health builder with nonexistent artifact paths must degrade safely.
    missing_root = Path("/nonexistent/invforge-pr07-smoke")
    missing_specs = [
        ArtifactSpec(key=key, path=missing_root / f"{key}.json")
        for key in REQUIRED_ARTIFACT_KEYS
    ]
    missing_health = health_mod.build_health_status(
        specs=missing_specs,
        mlops_loop_path=missing_root / "loop.json",
        comparison_path=missing_root / "comparison.json",
        bentoml_path=missing_root / "bento.json",
    )
    _check(
        missing_health["status"] in {"unavailable", "degraded"},
        f"expected unavailable/degraded for missing paths, got "
        f"{missing_health['status']!r}",
    )
    _check(
        REQUIRED_HEALTH_KEYS <= set(missing_health),
        "missing-path health payload missing required keys",
    )

    # 3. Health builder with real (default) paths returns full B3 shape.
    real_health = health_mod.build_health_status()
    _check(
        REQUIRED_HEALTH_KEYS <= set(real_health),
        f"real health payload missing keys: "
        f"{REQUIRED_HEALTH_KEYS - set(real_health)}",
    )
    _check(
        set(real_health["artifacts"]) == REQUIRED_ARTIFACT_KEYS,
        "real health artifacts keys mismatch",
    )
    _check(
        real_health["champion_challenger_decision"]
        in health_mod.ALLOWED_DECISIONS,
        "invalid champion/challenger decision value",
    )

    # 4. All B2 metrics are registered by name.
    metrics_mod.refresh_artifact_metrics()
    registered = metrics_mod.registered_metric_names()
    for name in metrics_mod.METRIC_NAMES:
        _check(name in registered, f"metric {name!r} not registered")

    # 5. No metric label value may be a path or contain path separators.
    offenders = metrics_mod.assert_no_path_label_values()
    _check(not offenders, f"path-like metric label values found: {offenders}")

    # Also confirm /metrics renders to Prometheus exposition bytes.
    payload, content_type = metrics_mod.render_latest()
    _check(isinstance(payload, bytes) and payload, "empty metrics payload")
    _check("text/plain" in content_type, f"unexpected content type {content_type!r}")


def main() -> int:
    try:
        run_smoke()
    except Exception as exc:  # noqa: BLE001 - smoke must never crash uncaught
        print(f"observability-smoke FAILED: {type(exc).__name__}: {exc}")
        return 1
    print("observability-smoke: all checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
