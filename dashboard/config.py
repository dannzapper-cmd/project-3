"""Dashboard runtime configuration (local vs cloud demo mode)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_TRUE_VALUES: frozenset[str] = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES: frozenset[str] = frozenset({"0", "false", "no", "off"})
_CLOUD_ENVS: frozenset[str] = frozenset({"demo", "cloud"})


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    return default


@dataclass(frozen=True)
class DashboardSettings:
    """Environment-backed settings for the Streamlit dashboard."""

    env: str = "local"
    demo_auth_enabled: bool = False
    demo_user: str = "reviewer"
    demo_password: str = ""
    fixtures_root: Path | None = None
    api_base_url: str = ""
    github_repo_url: str = "https://github.com/dannzapper-cmd/project-3"
    reviewer_guide_path: str = "docs/REVIEWER_DEMO_GUIDE.md"
    evidence_doc_path: str = "docs/evidence/PR14_CLOUD_RUN_LIVE_DEMO.md"

    @property
    def is_cloud_mode(self) -> bool:
        return self.env in _CLOUD_ENVS

    @property
    def show_demo_credentials_hint(self) -> bool:
        """Show portfolio demo credentials on the login page when safe."""

        if not self.demo_auth_enabled or not self.demo_password:
            return False
        explicit = os.getenv("INVFORGE_SHOW_DEMO_CREDENTIALS", "").strip().lower()
        if explicit in _TRUE_VALUES:
            return True
        if explicit in _FALSE_VALUES:
            return False
        return self.is_cloud_mode

    @property
    def read_only_banner(self) -> str:
        return "Read-only portfolio demo · synthetic data · not production"

    @property
    def mode_label(self) -> str:
        if self.is_cloud_mode:
            return "Cloud · fixture-backed read-only demo"
        return "Local · full pipeline artifacts"

    @classmethod
    def from_env(cls) -> "DashboardSettings":
        env = os.getenv("INVFORGE_ENV", cls.env).strip().lower() or cls.env
        is_cloud = env in _CLOUD_ENVS
        auth_default = is_cloud or _parse_bool(
            os.getenv("INVFORGE_DEMO_AUTH_ENABLED"), default=False
        )
        fixtures_raw = os.getenv("INVFORGE_DASHBOARD_FIXTURES_DIR", "").strip()
        fixtures_root = Path(fixtures_raw) if fixtures_raw else None
        if fixtures_root is None and is_cloud:
            fixtures_root = (
                Path(__file__).resolve().parent / "demo_fixtures"
            )
        return cls(
            env=env,
            demo_auth_enabled=_parse_bool(
                os.getenv("INVFORGE_DEMO_AUTH_ENABLED"), default=auth_default
            ),
            demo_user=os.getenv("INVFORGE_DEMO_USER", cls.demo_user),
            demo_password=os.getenv("INVFORGE_DEMO_PASSWORD", cls.demo_password),
            fixtures_root=fixtures_root,
            api_base_url=os.getenv(
                "INVFORGE_API_BASE_URL", cls.api_base_url
            ).rstrip("/"),
            github_repo_url=os.getenv(
                "INVFORGE_GITHUB_REPO_URL", cls.github_repo_url
            ).rstrip("/"),
            reviewer_guide_path=os.getenv(
                "INVFORGE_REVIEWER_GUIDE_PATH", cls.reviewer_guide_path
            ),
        )
