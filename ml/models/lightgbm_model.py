"""Global LightGBM demand forecasting baseline."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

from ml.features import CATEGORICAL_FEATURES, FEATURE_COLUMNS, TARGET_COLUMN


def _feature_columns(
    train_df: pd.DataFrame,
    *,
    excluded_features: Iterable[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Return (all_features, categorical_columns) without duplicates."""

    excluded = set(excluded_features or [])
    all_features = [col for col in FEATURE_COLUMNS if col not in excluded]
    for col in CATEGORICAL_FEATURES:
        if col in train_df.columns and col not in all_features and col not in excluded:
            all_features.append(col)
    cat_cols = [c for c in CATEGORICAL_FEATURES if c in all_features]
    return all_features, cat_cols


def train_lightgbm(
    train_df: pd.DataFrame,
    params: dict[str, Any],
) -> tuple[lgb.LGBMRegressor, list[str]]:
    """Train a single global LightGBM model on all series."""

    all_features, cat_cols = _feature_columns(train_df)

    X = train_df[all_features].copy()
    for col in cat_cols:
        X[col] = X[col].astype("category")

    y = train_df[TARGET_COLUMN].values

    model_params = {
        "objective": params.get("objective", "regression"),
        "learning_rate": params.get("learning_rate", 0.05),
        "num_leaves": params.get("num_leaves", 31),
        "max_depth": params.get("max_depth", -1),
        "n_estimators": params.get("n_estimators", 200),
        "min_child_samples": params.get("min_child_samples", 20),
        "subsample": params.get("subsample", 0.8),
        "colsample_bytree": params.get("colsample_bytree", 0.8),
        "random_state": params.get("random_state", 42),
        "verbose": params.get("verbose", -1),
    }

    model = lgb.LGBMRegressor(**model_params)
    model.fit(X, y, categorical_feature=cat_cols)
    return model, all_features


def predict_lightgbm(
    model: lgb.LGBMRegressor,
    df: pd.DataFrame,
    feature_names: list[str],
) -> np.ndarray:
    X = df[feature_names].copy()
    for col in CATEGORICAL_FEATURES:
        if col in X.columns:
            X[col] = X[col].astype("category")
    preds = model.predict(X)
    return np.maximum(preds, 0.0)


def train_quantile_models(
    train_df: pd.DataFrame,
    params: dict[str, Any],
    *,
    alphas: Iterable[float] = (0.1, 0.5, 0.9),
    excluded_features: Iterable[str] | None = None,
) -> tuple[dict[float, lgb.LGBMRegressor], list[str]]:
    """Train independent LightGBM quantile regressors for prediction intervals."""

    all_features, cat_cols = _feature_columns(
        train_df,
        excluded_features=excluded_features,
    )

    X = train_df[all_features].copy()
    for col in cat_cols:
        X[col] = X[col].astype("category")

    y = train_df[TARGET_COLUMN].values

    base_params = {
        "learning_rate": params.get("learning_rate", 0.05),
        "num_leaves": params.get("num_leaves", 31),
        "max_depth": params.get("max_depth", -1),
        "n_estimators": params.get("n_estimators", 200),
        "min_child_samples": params.get("min_child_samples", 20),
        "subsample": params.get("subsample", 0.8),
        "colsample_bytree": params.get("colsample_bytree", 0.8),
        "random_state": params.get("random_state", 42),
        "verbose": params.get("verbose", -1),
    }

    models: dict[float, lgb.LGBMRegressor] = {}
    for alpha in alphas:
        alpha = float(alpha)
        model = lgb.LGBMRegressor(
            **base_params,
            objective="quantile",
            metric="quantile",
            alpha=alpha,
        )
        model.fit(X, y, categorical_feature=cat_cols)
        models[alpha] = model

    return models, all_features


def predict_quantile_models(
    models: dict[float, lgb.LGBMRegressor],
    df: pd.DataFrame,
    feature_names: list[str],
) -> pd.DataFrame:
    """Return non-negative quantile predictions with columns named qXX."""

    predictions: dict[str, np.ndarray] = {}
    for alpha, model in sorted(models.items()):
        col = f"q{int(round(alpha * 100)):02d}"
        predictions[col] = predict_lightgbm(model, df, feature_names)
    return pd.DataFrame(predictions, index=df.index)
