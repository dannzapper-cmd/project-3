"""Runtime configuration for the InvForge API and data pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Environment-backed settings with safe defaults for local development."""

    inventree_base_url: str = "http://inventree.localhost:8080"
    inventree_api_token: str = "replace-me"
    data_dir: Path = Path("data")
    api_port: int = 8001
    inventree_timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            inventree_base_url=os.getenv(
                "INVENTREE_BASE_URL", cls.inventree_base_url
            ).rstrip("/"),
            inventree_api_token=os.getenv(
                "INVENTREE_API_TOKEN", cls.inventree_api_token
            ),
            data_dir=Path(os.getenv("INVFORGE_DATA_DIR", str(cls.data_dir))),
            api_port=int(os.getenv("INVFORGE_API_PORT", str(cls.api_port))),
            inventree_timeout_seconds=float(
                os.getenv(
                    "INVENTREE_TIMEOUT_SECONDS",
                    str(cls.inventree_timeout_seconds),
                )
            ),
        )

