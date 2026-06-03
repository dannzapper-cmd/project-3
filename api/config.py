"""Runtime configuration for the InvForge API and data pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Recognized deployment environments. ``local`` and ``ci`` keep the historical
# developer behavior (mutations allowed, strict health). ``demo`` and ``cloud``
# are the cloud-ready, read-only-by-default surfaces introduced in PR-10.
LOCAL_ENVS: frozenset[str] = frozenset({"local", "ci"})
CLOUD_ENVS: frozenset[str] = frozenset({"demo", "cloud"})
KNOWN_ENVS: frozenset[str] = LOCAL_ENVS | CLOUD_ENVS

_TRUE_VALUES: frozenset[str] = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES: frozenset[str] = frozenset({"0", "false", "no", "off"})


def _parse_bool(value: str | None, default: bool) -> bool:
    """Parse a boolean-ish env var, falling back to ``default`` when unset."""

    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    return default


@dataclass(frozen=True)
class Settings:
    """Environment-backed settings with safe defaults for local development.

    The PR-10 deployment fields (``env``, ``demo_mode``, ``allow_mutations``)
    default to the historical local behavior so existing tests and the local
    developer workflow are unchanged. ``Settings.from_env`` derives cloud-safe
    defaults (read-only, mutation-blocked) when ``INVFORGE_ENV`` is ``demo`` or
    ``cloud``.
    """

    inventree_base_url: str = "http://inventree.localhost:8080"
    inventree_api_token: str | None = "replace-me"
    inventree_username: str | None = None
    inventree_password: str | None = None
    data_dir: Path = Path("data")
    api_port: int = 8001
    inventree_timeout_seconds: float = 10.0
    env: str = "local"
    demo_mode: bool = False
    allow_mutations: bool = True

    @property
    def is_cloud_env(self) -> bool:
        """True when running in a cloud-facing (demo/cloud) environment."""

        return self.env in CLOUD_ENVS

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.getenv("INVFORGE_ENV", cls.env).strip().lower() or cls.env
        is_cloud = env in CLOUD_ENVS
        # Cloud/demo surfaces default to read-only with mutations blocked; the
        # health endpoint reports "up" even when local artifacts are absent so
        # provider health checks pass on a fresh demo container.
        demo_mode = _parse_bool(os.getenv("INVFORGE_DEMO_MODE"), default=is_cloud)
        allow_mutations = _parse_bool(
            os.getenv("INVFORGE_ALLOW_MUTATIONS"), default=not is_cloud
        )
        return cls(
            inventree_base_url=os.getenv(
                "INVENTREE_BASE_URL", cls.inventree_base_url
            ).rstrip("/"),
            inventree_api_token=os.getenv(
                "INVENTREE_API_TOKEN", cls.inventree_api_token
            ),
            inventree_username=os.getenv("INVENTREE_USERNAME"),
            inventree_password=os.getenv("INVENTREE_PASSWORD"),
            data_dir=Path(os.getenv("INVFORGE_DATA_DIR", str(cls.data_dir))),
            api_port=int(os.getenv("INVFORGE_API_PORT", str(cls.api_port))),
            inventree_timeout_seconds=float(
                os.getenv(
                    "INVENTREE_TIMEOUT_SECONDS",
                    str(cls.inventree_timeout_seconds),
                )
            ),
            env=env,
            demo_mode=demo_mode,
            allow_mutations=allow_mutations,
        )

