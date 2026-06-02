"""StatsForecast (Nixtla) statistical baselines by demand pattern."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from statsforecast import StatsForecast
from statsforecast.models import (
    AutoETS,
    CrostonClassic,
    CrostonSBA,
    SeasonalNaive,
)

logger = logging.getLogger(__name__)

REGULAR_MODELS = {"AutoETS", "SeasonalNaive"}
INTERMITTENT_MODELS = {"CrostonClassic", "CrostonSBA", "SBA"}


def _build_model(name: str, season_length: int):
    if name == "AutoETS":
        return AutoETS(season_length=season_length)
    if name == "SeasonalNaive":
        return SeasonalNaive(season_length=season_length)
    if name == "CrostonClassic":
        return CrostonClassic()
    if name in ("SBA", "CrostonSBA"):
        return CrostonSBA()
    raise ValueError(f"Unknown StatsForecast model: {name}")


def _to_statsforecast_format(df: pd.DataFrame) -> pd.DataFrame:
    out = df[["part_id", "date", "quantity_demand"]].copy()
    out = out.rename(
        columns={"part_id": "unique_id", "date": "ds", "quantity_demand": "y"}
    )
    out["ds"] = pd.to_datetime(out["ds"])
    return out


def _forecast_batch(
    pattern_train: pd.DataFrame,
    *,
    model_names: list[str],
    season_length: int,
    horizon: int,
    level: list[int] | None = None,
) -> pd.DataFrame:
    """Run StatsForecast; fall back to simpler models on short-series failures."""

    attempts = [model_names]
    if "AutoETS" in model_names:
        fallback = [n for n in model_names if n != "AutoETS"] or ["SeasonalNaive"]
        attempts.append(fallback)

    last_error: Exception | None = None
    for names in attempts:
        try:
            models = [_build_model(n, season_length) for n in names]
            sf = StatsForecast(models=models, freq="D", n_jobs=1)
            forecasts = sf.forecast(df=pattern_train, h=horizon, level=level)
            forecasts = forecasts.reset_index()
            skip_cols = ("unique_id", "ds", "index")
            model_cols = [c for c in forecasts.columns if c not in skip_cols]
            if not model_cols:
                raise RuntimeError("No forecast columns returned")
            first_name = names[0]
            best_col = first_name if first_name in forecasts.columns else model_cols[0]
            forecasts = forecasts.rename(columns={best_col: "yhat"})
            return forecasts
        except Exception as exc:
            last_error = exc
            logger.warning("StatsForecast failed for %s: %s", names, exc)

    raise RuntimeError("StatsForecast forecasting failed") from last_error


def fit_predict_statsforecast(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    parts_patterns: dict[str, str],
    *,
    season_length: int = 7,
    regular_model_names: list[str] | None = None,
    intermittent_model_names: list[str] | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Fit pattern-specific StatsForecast models and return test-set predictions."""

    regular_model_names = regular_model_names or ["AutoETS", "SeasonalNaive"]
    intermittent_model_names = intermittent_model_names or [
        "CrostonClassic",
        "CrostonSBA",
    ]

    train_sf = _to_statsforecast_format(train_df)
    test_sf = _to_statsforecast_format(test_df)

    horizon = int(test_sf.groupby("unique_id", observed=True)["ds"].nunique().max())
    if horizon < 1:
        raise ValueError("Test horizon must be at least 1 day")

    all_preds: list[pd.DataFrame] = []
    model_usage: dict[str, list[str]] = {"regular": [], "intermittent": []}

    for pattern, model_names, allowed in [
        ("regular", regular_model_names, REGULAR_MODELS),
        ("intermittent", intermittent_model_names, INTERMITTENT_MODELS),
    ]:
        series_ids = [
            pid
            for pid, pat in parts_patterns.items()
            if pat == pattern and pid in train_sf["unique_id"].unique()
        ]
        if not series_ids:
            continue

        valid_names = [n for n in model_names if n in allowed]
        if not valid_names:
            continue

        pattern_train = train_sf[train_sf["unique_id"].isin(series_ids)]
        model_usage[pattern] = valid_names
        forecasts = _forecast_batch(
            pattern_train,
            model_names=valid_names,
            season_length=season_length,
            horizon=horizon,
        )
        all_preds.append(forecasts)

    if not all_preds:
        raise RuntimeError("No StatsForecast predictions were generated")

    combined = pd.concat(all_preds, ignore_index=True)
    merged = test_sf.merge(combined, on=["unique_id", "ds"], how="left")
    merged["yhat"] = merged["yhat"].fillna(0.0)

    return merged["yhat"].to_numpy(), model_usage


def _interval_columns(
    forecasts: pd.DataFrame,
    *,
    level: int,
) -> tuple[str | None, str | None]:
    suffixes = (f"-lo-{level}", f"-hi-{level}")
    lower = next((c for c in forecasts.columns if c.endswith(suffixes[0])), None)
    upper = next((c for c in forecasts.columns if c.endswith(suffixes[1])), None)
    return lower, upper


def fit_predict_statsforecast_intervals(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    parts_patterns: dict[str, str],
    *,
    season_length: int = 7,
    regular_model_names: list[str] | None = None,
    intermittent_model_names: list[str] | None = None,
    level: int = 80,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fit pattern-specific StatsForecast models and return native intervals."""

    regular_model_names = regular_model_names or ["AutoETS", "SeasonalNaive"]
    intermittent_model_names = intermittent_model_names or [
        "CrostonClassic",
        "CrostonSBA",
    ]

    train_sf = _to_statsforecast_format(train_df)
    test_sf = _to_statsforecast_format(test_df)

    horizon = int(test_sf.groupby("unique_id", observed=True)["ds"].nunique().max())
    if horizon < 1:
        raise ValueError("Test horizon must be at least 1 day")

    all_preds: list[pd.DataFrame] = []
    model_usage: dict[str, list[str]] = {"regular": [], "intermittent": []}

    for pattern, model_names, allowed in [
        ("regular", regular_model_names, REGULAR_MODELS),
        ("intermittent", intermittent_model_names, INTERMITTENT_MODELS),
    ]:
        series_ids = [
            pid
            for pid, pat in parts_patterns.items()
            if pat == pattern and pid in train_sf["unique_id"].unique()
        ]
        if not series_ids:
            continue

        valid_names = [n for n in model_names if n in allowed]
        if not valid_names:
            continue

        pattern_train = train_sf[train_sf["unique_id"].isin(series_ids)]
        model_usage[pattern] = valid_names
        forecasts = _forecast_batch(
            pattern_train,
            model_names=valid_names,
            season_length=season_length,
            horizon=horizon,
            level=[level],
        )
        lower_col, upper_col = _interval_columns(forecasts, level=level)
        keep_cols = ["unique_id", "ds", "yhat"]
        if lower_col and upper_col:
            forecasts = forecasts.rename(
                columns={lower_col: "yhat_lower", upper_col: "yhat_upper"}
            )
            keep_cols.extend(["yhat_lower", "yhat_upper"])
        all_preds.append(forecasts[keep_cols])

    if not all_preds:
        raise RuntimeError("No StatsForecast interval predictions were generated")

    combined = pd.concat(all_preds, ignore_index=True)
    merged = test_sf.merge(combined, on=["unique_id", "ds"], how="left")
    merged = merged.rename(columns={"unique_id": "part_id", "ds": "date"})
    for col in ("yhat", "yhat_lower", "yhat_upper"):
        if col not in merged.columns:
            merged[col] = np.nan

    interval_cols = ["part_id", "date", "y", "yhat", "yhat_lower", "yhat_upper"]
    return merged[interval_cols], model_usage
