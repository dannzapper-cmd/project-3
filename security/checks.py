"""Run Bandit, pip-audit, and detect-secrets; fail if any tool fails."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_step(name: str, command: list[str]) -> int:
    print(f"\n=== {name} ===")
    result = subprocess.run(command, cwd=REPO_ROOT, check=False)
    status = "PASS" if result.returncode == 0 else "FAIL"
    print(f"{name}: {status} (exit {result.returncode})")
    return result.returncode


def main() -> int:
    results: list[tuple[str, int]] = []

    results.append(
        (
            "bandit",
            _run_step(
                "bandit",
                [
                    "uv",
                    "run",
                    "--group",
                    "security",
                    "bandit",
                    "-r",
                    "security/",
                    "api/",
                    "-ll",
                    "-q",
                ],
            ),
        )
    )
    results.append(
        (
            "pip-audit",
            _run_step("pip-audit", ["uvx", "pip-audit"]),
        )
    )
    results.append(
        (
            "detect-secrets",
            _run_step(
                "detect-secrets",
                [
                    "uv",
                    "run",
                    "detect-secrets",
                    "scan",
                    "--baseline",
                    ".secrets.baseline",
                ],
            ),
        )
    )

    failed = [name for name, code in results if code != 0]
    if failed:
        print(f"\nSecurity check failed: {', '.join(failed)}", file=sys.stderr)
        return 1

    print("\nAll security checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
