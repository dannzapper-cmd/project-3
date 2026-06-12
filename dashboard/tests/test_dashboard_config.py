"""Tests for dashboard cloud/demo configuration."""

from __future__ import annotations

from pathlib import Path

import pytest

from dashboard.config import DashboardSettings


def test_cloud_mode_uses_bundled_fixtures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INVFORGE_ENV", "cloud")
    monkeypatch.delenv("INVFORGE_DASHBOARD_FIXTURES_DIR", raising=False)
    import importlib

    import dashboard.paths as paths

    importlib.reload(paths)
    assert "demo_fixtures" in str(paths.DEFAULT_SYNTHETIC_DIR)
    assert "demo_fixtures" in str(paths.DEFAULT_DECISION_DIR)


def test_demo_auth_defaults_cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INVFORGE_ENV", "cloud")
    monkeypatch.delenv("INVFORGE_DEMO_AUTH_ENABLED", raising=False)
    settings = DashboardSettings.from_env()
    assert settings.is_cloud_mode
    assert settings.demo_auth_enabled is True


def test_local_auth_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INVFORGE_ENV", "local")
    monkeypatch.delenv("INVFORGE_DEMO_AUTH_ENABLED", raising=False)
    settings = DashboardSettings.from_env()
    assert settings.demo_auth_enabled is False
    assert settings.show_demo_credentials_hint is False


def test_cloud_credentials_hint_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INVFORGE_ENV", "cloud")
    monkeypatch.setenv("INVFORGE_DEMO_PASSWORD", "invforge-demo")
    settings = DashboardSettings.from_env()
    assert settings.show_demo_credentials_hint is True
    assert settings.mode_label.startswith("Cloud")


def test_fixtures_exist_in_repo() -> None:
    root = Path(__file__).resolve().parents[1] / "demo_fixtures"
    assert (root / "decision" / "decision_summary.json").is_file()
    assert (root / "mlops" / "mlops_loop_summary.json").is_file()
    assert (root / "synthetic" / "output" / "parts.csv").is_file()
