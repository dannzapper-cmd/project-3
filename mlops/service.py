"""Minimal BentoML service scaffold for the champion forecasting model.

This is a *local, illustrative* serving definition only. PR-05 does not deploy
it, build a Docker image, or run it in Kubernetes (that is PR-10/PR-11 scope).
It exists so the packaged champion model has a clear, runnable-by-hand serving
entrypoint:

    uv run --group ml --group mlops bentoml serve mlops.service:DemandForecastService

The model must first be packaged into the local store via ``make mlops-loop``.
"""

from __future__ import annotations

from typing import Any

import bentoml

MODEL_NAME = "invforge_demand_forecast"


@bentoml.service(name="invforge_demand_forecast")
class DemandForecastService:
    """Wraps the champion LightGBM demand forecasting model for local serving."""

    def __init__(self) -> None:
        self.model = bentoml.models.get(f"{MODEL_NAME}:latest")
        self.predictor = self.model.load_model()

    @bentoml.api
    def predict(self, instances: list[list[float]]) -> dict[str, Any]:
        """Return non-negative demand predictions for engineered feature rows."""

        import numpy as np

        predictions = self.predictor.predict(np.asarray(instances, dtype=float))
        return {
            "predictions": [float(max(0.0, value)) for value in predictions],
            "warning": "Synthetic-data model; not a production forecast.",
        }
