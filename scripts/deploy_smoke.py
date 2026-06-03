#!/usr/bin/env python3
"""Read-only deploy smoke check for the InvForge AI Operations Layer (PR-10).

Verifies that a deployed (or locally running) AI Operations API is alive and
serving the SAFE, read-only surface. It is deliberately constrained:

  * Only GET endpoints classified as SAFE in docs/deployment-contract.md are
    called.
  * Mutation / training / registry / security endpoints are NEVER called. Any
    URL path containing a forbidden token (retrain, rollback, promote, register,
    delete, audit, scan, ingest) is refused in code, not just in docs.
  * No secrets are required and no request body is sent.
  * Uses only the Python standard library (urllib) so it needs no extra runtime
    dependency.

Exit codes:
  0  all checks passed
  1  at least one check failed (prints which check, expected vs actual, and a
     suggested fix)

Usage:
  python scripts/deploy_smoke.py --base-url https://my-service.example.run.app
  python scripts/deploy_smoke.py                      # defaults to localhost:$PORT
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass

# Endpoint path fragments that indicate a mutating / sensitive operation. The
# smoke check must never call these, even if a future endpoint is added.
FORBIDDEN_PATH_TOKENS: tuple[str, ...] = (
    "retrain",
    "rollback",
    "promote",
    "register",
    "delete",
    "audit",
    "scan",
    "ingest",
)


@dataclass(frozen=True)
class Check:
    """A single read-only probe."""

    name: str
    path: str
    required: bool
    expected_keys: tuple[str, ...] = ()


# SAFE, read-only checks only. See docs/deployment-contract.md endpoint table.
CHECKS: tuple[Check, ...] = (
    Check(
        name="health",
        path="/health",
        required=True,
        expected_keys=("status", "pr_stage"),
    ),
    Check(
        name="inventory-status",
        path="/v1/inventory/status",
        required=False,
        expected_keys=("status", "env"),
    ),
    Check(
        name="data-summary",
        path="/v1/data/summary",
        required=False,
    ),
)


class SmokeError(Exception):
    """A smoke check failure with an actionable message."""


def _assert_safe_path(path: str) -> None:
    lowered = path.lower()
    for token in FORBIDDEN_PATH_TOKENS:
        if token in lowered:
            raise SmokeError(
                f"refusing to call '{path}': contains forbidden token '{token}'. "
                "deploy_smoke.py is read-only and must never call mutation "
                "endpoints."
            )


def _get(url: str, timeout: float) -> tuple[int, bytes]:
    request = urllib.request.Request(url, method="GET")  # noqa: S310 (http(s) only)
    if not url.startswith(("http://", "https://")):
        raise SmokeError(f"unsupported URL scheme for '{url}' (use http/https)")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.status, response.read()
    except urllib.error.HTTPError as exc:  # non-2xx still returns a response body
        return exc.code, exc.read()
    except urllib.error.URLError as exc:
        raise SmokeError(f"could not reach {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise SmokeError(f"timed out after {timeout}s calling {url}") from exc


def _run_check(base_url: str, check: Check, timeout: float) -> bool:
    _assert_safe_path(check.path)
    url = base_url.rstrip("/") + check.path
    status, body = _get(url, timeout)

    if status != 200:
        if check.required:
            raise SmokeError(
                f"[{check.name}] GET {check.path} returned {status}, expected 200.\n"
                f"  Fix: confirm the service is deployed and that /health is the "
                f"correct path. In demo/cloud mode /health returns 200 even "
                f"without local artifacts."
            )
        print(f"  - {check.name}: GET {check.path} -> {status} (optional, skipped)")
        return True

    try:
        payload = json.loads(body)
    except (ValueError, json.JSONDecodeError) as exc:
        raise SmokeError(
            f"[{check.name}] GET {check.path} returned non-JSON body.\n"
            f"  Fix: ensure the endpoint returns a JSON object. ({exc})"
        ) from exc

    if not isinstance(payload, dict):
        raise SmokeError(
            f"[{check.name}] GET {check.path} returned a non-object JSON payload."
        )

    missing = [key for key in check.expected_keys if key not in payload]
    if missing:
        raise SmokeError(
            f"[{check.name}] GET {check.path} 200 OK but missing keys: "
            f"{', '.join(missing)}.\n"
            f"  Expected keys: {', '.join(check.expected_keys)}\n"
            f"  Got keys: {', '.join(sorted(payload))}"
        )

    detail = ""
    if "status" in payload:
        detail = f" (status={payload['status']})"
    print(f"  - {check.name}: GET {check.path} -> 200 OK{detail}")
    return True


def _default_base_url() -> str:
    port = os.environ.get("PORT") or os.environ.get("INVFORGE_API_PORT") or "8001"
    return f"http://localhost:{port}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=_default_base_url(),
        help=(
            "Base URL of the deployed AI Operations API "
            "(default: http://localhost:$PORT or :8001)."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Per-request timeout in seconds (default: 10).",
    )
    args = parser.parse_args(argv)

    base_url = args.base_url
    if not base_url.startswith(("http://", "https://")):
        print(
            f"ERROR: --base-url must start with http:// or https:// (got "
            f"'{base_url}')",
            file=sys.stderr,
        )
        return 1

    print(f"InvForge deploy smoke (read-only) against {base_url}")
    failures: list[str] = []
    for check in CHECKS:
        try:
            _run_check(base_url, check, args.timeout)
        except SmokeError as exc:
            failures.append(str(exc))
            print(f"  - {check.name}: FAILED", file=sys.stderr)

    if failures:
        print("\nSmoke check FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"\n{failure}", file=sys.stderr)
        return 1

    print("\nSmoke check PASSED (read-only).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
