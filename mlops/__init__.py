"""InvForge PR-05 MLOps loop.

A minimal, local, deterministic, offline MLOps loop layered on top of the
PR-03 forecasting baseline and PR-04 decision intelligence. It produces:

* Evidently offline data drift / data quality reports on a temporal
  reference/current split.
* An MLflow model registry / metadata summary for the current demand
  forecasting model.
* A champion/challenger comparison built from existing PR-03/PR-04 artifacts.
* Optional minimal BentoML packaging of the champion model.

Nothing here trains models, mutates PR-03/PR-04 metric files, or requires a
network connection or a running service.
"""

from __future__ import annotations

SCHEMA_VERSION = "1.0"

__all__ = ["SCHEMA_VERSION"]
