"""Pytest hooks: resolve imports to the repository ``security`` package."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_root = str(_REPO_ROOT)
if _root not in sys.path:
    sys.path.insert(0, _root)

_stale = sys.modules.get("security")
if _stale is not None and not hasattr(_stale, "audit"):
    for key in list(sys.modules):
        if key == "security" or key.startswith("security."):
            del sys.modules[key]
