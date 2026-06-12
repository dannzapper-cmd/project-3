#!/usr/bin/env bash
# PR-13 screenshot capture wrapper (dev-only; Playwright not a project dependency).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "=== PR-13 screenshot capture ==="

if ! uv run python -c "import playwright" 2>/dev/null; then
  echo "Installing Playwright in project venv (dev-only, not in pyproject deps) ..."
  uv pip install playwright
  uv run python -m playwright install chromium
fi

uv run python scripts/capture_pr13_screenshots.py
echo "See docs/assets/screenshots/SCREENSHOT_MANIFEST.md"
