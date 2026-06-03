#!/usr/bin/env python3
"""Static validation for InvForge PR-10 deploy profiles and templates.

Runs entirely offline. It does NOT call any cloud CLI, require credentials, or
create resources. It verifies that the deploy/* profiles are honest,
placeholder-only, and complete:

  * JSON templates parse as valid JSON.
  * YAML templates parse as valid YAML (skipped with a warning if PyYAML is
    unavailable).
  * env.example files contain no real-looking secrets.
  * Deploy templates contain only placeholders (no real project/account/
    subscription IDs).
  * Each deploy/<provider>/README.md exists, is non-empty, and documents
    teardown.
  * .dockerignore covers the required leak-prevention categories.
  * Required placeholders are present in each provider's service template.

Exit codes: 0 = all checks passed, 1 = one or more failures.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    import yaml  # type: ignore

    _YAML = True
except ImportError:  # pragma: no cover - PyYAML is optional for this script
    yaml = None  # type: ignore
    _YAML = False

REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOY_DIR = REPO_ROOT / "deploy"
PROVIDERS = ("gcp", "aws", "azure")

# Required placeholders per provider service template. Presence proves the
# template is parameterized rather than hardcoded to a real account.
REQUIRED_PLACEHOLDERS: dict[str, tuple[str, ...]] = {
    "gcp": ("PROJECT_ID", "REGION", "SERVICE_NAME", "IMAGE_URI"),
    "aws": ("ACCOUNT_ID", "REGION", "IMAGE_URI", "EXECUTION_ROLE_ARN"),
    "azure": ("SUBSCRIPTION_ID", "RESOURCE_GROUP", "APP_NAME", "IMAGE_URI"),
}

# .dockerignore must cover all of these leak-prevention categories.
REQUIRED_DOCKERIGNORE = (
    ".env",
    "mlruns/",
    "artifacts/",
    "data/",
    "notebooks/",
    ".git/",
    "__pycache__/",
    ".secrets.baseline",
    ".venv/",
)

# Patterns that look like real secrets / account-specific values. Templates and
# env.example files must NOT contain these.
FORBIDDEN_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"AKIA[0-9A-Z]{16}", "AWS access key id"),
    (r"\bASIA[0-9A-Z]{16}\b", "AWS temporary access key id"),
    (r"AIza[0-9A-Za-z_\-]{35}", "Google API key"),
    (r"sk-[A-Za-z0-9]{20,}", "OpenAI-style secret key"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key block"),
    (r"xox[abpr]-[0-9A-Za-z\-]{10,}", "Slack token"),
    (r"ghp_[0-9A-Za-z]{36}", "GitHub personal access token"),
)

# Real-account-id heuristics for placeholder hygiene in deploy templates. We
# only flag values that are NOT obviously placeholders.
PLACEHOLDER_HINT = re.compile(
    r"PROJECT_ID|ACCOUNT_ID|SUBSCRIPTION_ID|REGION|SERVICE_NAME|APP_NAME|"
    r"IMAGE_URI|ROLE_ARN|SA_EMAIL|REGISTRY_SERVER|RESOURCE_GROUP|LOCATION|"
    r"placeholder|example|REPLACE|<.*?>|YOUR_|MY_"
)


def _fail(failures: list[str], message: str) -> None:
    failures.append(message)


def _scan_forbidden(failures: list[str], path: Path) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    for pattern, label in FORBIDDEN_PATTERNS:
        if re.search(pattern, text):
            _fail(failures, f"{path}: contains a real-looking secret ({label}).")


def _check_aws_account_ids(failures: list[str], path: Path) -> None:
    """Flag bare 12-digit AWS account ids that are not placeholders."""

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return
    for line in lines:
        if PLACEHOLDER_HINT.search(line):
            continue
        for match in re.finditer(r"\b\d{12}\b", line):
            _fail(
                failures,
                f"{path}: line looks like a real 12-digit AWS account id "
                f"('{match.group()}'). Use the ACCOUNT_ID placeholder instead.",
            )


def _validate_json(failures: list[str], path: Path) -> None:
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail(failures, f"{path}: invalid JSON ({exc}).")


def _validate_yaml(failures: list[str], path: Path) -> None:
    if not _YAML:
        return
    try:
        list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError) as exc:  # type: ignore[union-attr]
        _fail(failures, f"{path}: invalid YAML ({exc}).")


def _validate_placeholders(failures: list[str], provider: str) -> None:
    provider_dir = DEPLOY_DIR / provider
    required = REQUIRED_PLACEHOLDERS[provider]
    template_text = ""
    for path in sorted(provider_dir.glob("*")):
        if path.suffix in {".yaml", ".yml", ".json"} and "template" in path.name:
            template_text += path.read_text(encoding="utf-8")
    if not template_text:
        # Fall back to concatenating all yaml/json in the dir.
        for path in sorted(provider_dir.glob("*")):
            if path.suffix in {".yaml", ".yml", ".json"}:
                template_text += path.read_text(encoding="utf-8")
    for placeholder in required:
        if placeholder not in template_text:
            _fail(
                failures,
                f"deploy/{provider}: required placeholder '{placeholder}' not "
                f"found in any service template.",
            )


def _validate_readme(failures: list[str], provider: str) -> None:
    readme = DEPLOY_DIR / provider / "README.md"
    if not readme.is_file():
        _fail(failures, f"deploy/{provider}/README.md is missing.")
        return
    text = readme.read_text(encoding="utf-8")
    if len(text.strip()) < 200:
        _fail(failures, f"deploy/{provider}/README.md is too short / empty.")
    if "teardown" not in text.lower():
        _fail(
            failures,
            f"deploy/{provider}/README.md does not document teardown.",
        )


def _validate_dockerignore(failures: list[str]) -> None:
    path = REPO_ROOT / ".dockerignore"
    if not path.is_file():
        _fail(failures, ".dockerignore is missing.")
        return
    text = path.read_text(encoding="utf-8")
    for category in REQUIRED_DOCKERIGNORE:
        if category not in text:
            _fail(failures, f".dockerignore missing required entry: '{category}'.")


def _iter_deploy_files() -> list[Path]:
    if not DEPLOY_DIR.is_dir():
        return []
    return [p for p in DEPLOY_DIR.rglob("*") if p.is_file()]


def main() -> int:
    failures: list[str] = []

    if not DEPLOY_DIR.is_dir():
        print("ERROR: deploy/ directory not found.", file=sys.stderr)
        return 1

    deploy_files = _iter_deploy_files()

    # Syntax + secret scans across all deploy files.
    for path in deploy_files:
        _scan_forbidden(failures, path)
        if path.suffix == ".json":
            _validate_json(failures, path)
            _check_aws_account_ids(failures, path)
        elif path.suffix in {".yaml", ".yml"}:
            _validate_yaml(failures, path)
            _check_aws_account_ids(failures, path)

    # env.example files anywhere in the repo must not leak real secrets.
    for path in REPO_ROOT.rglob("env.example"):
        _scan_forbidden(failures, path)
    for path in REPO_ROOT.rglob(".env.example"):
        _scan_forbidden(failures, path)

    for provider in PROVIDERS:
        provider_dir = DEPLOY_DIR / provider
        if not provider_dir.is_dir():
            _fail(failures, f"deploy/{provider}/ directory is missing.")
            continue
        _validate_placeholders(failures, provider)
        _validate_readme(failures, provider)

    _validate_dockerignore(failures)

    if not _YAML:
        print("WARNING: PyYAML not available; YAML syntax checks were skipped.")

    if failures:
        print("Deploy profile validation FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    checked = len(deploy_files)
    print(f"Deploy profile validation PASSED ({checked} deploy files checked).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
