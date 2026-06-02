"""Global LightGBM demand forecasting baseline."""

from __future__ import annotations

from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

from ml.features import CATEGORICAL_FEATURES, FEATURE_COLUMNS, TARGET_COLUMN


def _feature_columns(train_df: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Return (all_features, categorical_columns) without duplicates."""

    all_features = FEATURE_COLUMNS.copy()
    for col in CATEGORICAL_FEATURES:
        if col in train_df.columns and col not in all_features:
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
