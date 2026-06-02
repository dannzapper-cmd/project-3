"""Configuration loading for the PR-05 MLOps loop."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_MLOPS_CONFIG_PATH = Path("mlops/config.yaml")
DEFAULT_ML_CONFIG_PATH = Path("ml/config.yaml")


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Configuration at {path} must be a mapping")
    return data


def load_mlops_config(
    path: Path = DEFAULT_MLOPS_CONFIG_PATH,
) -> dict[str, Any]:
    """Load the MLOps loop configuration file."""

    return load_yaml(path)


def load_ml_config(path: Path = DEFAULT_ML_CONFIG_PATH) -> dict[str, Any]:
    """Load the PR-03/PR-04 configuration (read-only) for shared settings."""

    if not path.exists():
        return {}
    return load_yaml(path)
