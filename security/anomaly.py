"""IsolationForest-based anomaly detection over movement features."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd
from sklearn.ensemble import IsolationForest

from security.constants import (
    ANOMALY_CONTAMINATION,
    ANOMALY_FEATURES,
    ANOMALY_N_ESTIMATORS,
    FEATURES_USED_STRING,
    MIN_SAMPLES_FOR_ANOMALY,
    MOVEMENT_TYPE_ENCODING,
    RANDOM_STATE,
)

if TYPE_CHECKING:
    from security.audit import AuditLogger


def _encode_movement_type(value: Any) -> int:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return MOVEMENT_TYPE_ENCODING["unknown"]
    key = str(value).strip().lower()
    return MOVEMENT_TYPE_ENCODING.get(key, MOVEMENT_TYPE_ENCODING["unknown"])


def _build_feature_frame(movements: pd.DataFrame) -> pd.DataFrame:
    df = movements.copy()
    df["quantity"] = df["quantity"].astype(float)
    df["movement_type_encoded"] = df["movement_type"].map(_encode_movement_type)
    dates = pd.to_datetime(df["date"])
    df["day_of_week"] = dates.dt.dayofweek.astype(int)
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)

    zscores: list[float] = []
    for _, row in df.iterrows():
        part_id = str(row["part_id"])
        part_qty = df.loc[df["part_id"] == part_id, "quantity"].astype(float)
        if len(part_qty) < 3:
            zscores.append(0.0)
            continue
        mean = float(part_qty.mean())
        std = float(part_qty.std())
        if std == 0:
            zscores.append(0.0)
        else:
            zscores.append((float(row["quantity"]) - mean) / std)
    df["quantity_zscore_per_part"] = zscores
    return df


class AnomalyDetector:
    """Wraps IsolationForest with deterministic parameters and sample guards."""

    def __init__(
        self,
        movements: pd.DataFrame,
        audit: AuditLogger | None = None,
    ) -> None:
        self._movements = movements.copy()
        self._audit = audit
        self._features = _build_feature_frame(self._movements)
        self._insufficient_zscore_parts: set[str] = set()
        for part_id, group in self._movements.groupby("part_id"):
            if len(group) < 3:
                self._insufficient_zscore_parts.add(str(part_id))

    @property
    def insufficient_zscore_parts(self) -> set[str]:
        return set(self._insufficient_zscore_parts)

    def detect(self) -> pd.DataFrame:
        n_samples = len(self._features)
        movement_ids = self._movements["movement_id"].astype(str).tolist()
        part_ids = self._movements["part_id"].astype(str).tolist()
        dates = self._movements["date"].astype(str).tolist()
        quantities = self._features["quantity"].tolist()

        if n_samples < MIN_SAMPLES_FOR_ANOMALY:
            if self._audit is not None:
                self._audit.log(
                    event_type="SYSTEM_CHECK",
                    severity="WARNING",
                    actor="system",
                    description=(
                        "Insufficient samples for anomaly detection: "
                        f"n={n_samples}, minimum={MIN_SAMPLES_FOR_ANOMALY}, skipped."
                    ),
                )
            return pd.DataFrame(
                {
                    "movement_id": movement_ids,
                    "part_id": part_ids,
                    "date": dates,
                    "quantity": quantities,
                    "anomaly_score": [0.0] * n_samples,
                    "is_anomaly": [0] * n_samples,
                    "features_used": [FEATURES_USED_STRING] * n_samples,
                }
            )

        matrix = self._features[ANOMALY_FEATURES].to_numpy(dtype=float)
        model = IsolationForest(
            contamination=ANOMALY_CONTAMINATION,
            random_state=RANDOM_STATE,
            n_estimators=ANOMALY_N_ESTIMATORS,
        )
        model.fit(matrix)
        predictions = model.predict(matrix)
        scores = model.decision_function(matrix)

        is_anomaly = [1 if pred == -1 else 0 for pred in predictions]

        return pd.DataFrame(
            {
                "movement_id": movement_ids,
                "part_id": part_ids,
                "date": dates,
                "quantity": quantities,
                "anomaly_score": scores.astype(float),
                "is_anomaly": is_anomaly,
                "features_used": [FEATURES_USED_STRING] * n_samples,
            }
        )
