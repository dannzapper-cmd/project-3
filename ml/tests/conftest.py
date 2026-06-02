"""Shared fixtures for ML tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


@pytest.fixture(scope="session")
def synthetic_dir() -> Path:
    root = Path(__file__).resolve().parents[2]
    output = root / "data" / "synthetic" / "output"
    if not output.exists():
        import subprocess
        import sys

        generator = root / "data" / "synthetic" / "generate_inventory_data.py"
        subprocess.run(
            [sys.executable, str(generator), "--output", str(output), "--seed", "42"],
            check=True,
        )
    return output


@pytest.fixture
def demand_table(synthetic_dir: Path) -> pd.DataFrame:
    from ml.data import load_demand_training_table

    return load_demand_training_table(synthetic_dir)
