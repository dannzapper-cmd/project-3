"""InvForge PR-09 local retraining pipeline.

A local, reproducible, auditable retraining lifecycle layered on the PR-03
forecasting baseline and the PR-05 MLOps loop. It uses ZenML as a *local* DAG
runner with typed steps, Optuna for bounded hyperparameter tuning, and the
existing MLflow registry/alias conventions for champion/challenger promotion
and rollback.

Nothing here is cloud, Kubernetes, or scheduled. Promotion is gated and
conservative; rejected/failed candidates can never overwrite the current
champion; and a safe rollback path (MLflow aliases when available, otherwise a
rollback manifest) is always produced.
"""

from __future__ import annotations

# Stable, documented artifact schema versions. Bump only with a documented
# migration so the dashboard / QA layers can rely on them.
SUMMARY_SCHEMA_VERSION = "1.0"
ROLLBACK_SCHEMA_VERSION = "1.0"
ERROR_ANALYSIS_SCHEMA_VERSION = "1.0"

__all__ = [
    "SUMMARY_SCHEMA_VERSION",
    "ROLLBACK_SCHEMA_VERSION",
    "ERROR_ANALYSIS_SCHEMA_VERSION",
]
