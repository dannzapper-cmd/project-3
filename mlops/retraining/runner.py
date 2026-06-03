"""Command-line entry point for the PR-09 retraining pipeline.

Subcommands:

* ``retrain``   -- run the ZenML retraining pipeline (``--mode smoke|full``,
  optional ``--tune``).
* ``check``     -- validate the generated retraining artifacts against the
  stable schemas (no training, no mutation).
* ``rollback``  -- inspect/execute rollback. DRY RUN by default; requires
  ``--confirm`` (or ``ROLLBACK_CONFIRM=true``) to mutate the champion alias.

ZenML is forced into a fully local, offline, no-analytics mode here. No remote
stack, no ZenML cloud, no scheduler.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

# Configure ZenML for local-only, offline, quiet operation BEFORE it is imported
# anywhere downstream. Local SQLite default stack only (AA-4).
os.environ.setdefault("ZENML_ANALYTICS_OPT_IN", "false")
os.environ.setdefault("ZENML_LOGGING_VERBOSITY", "ERROR")
os.environ.setdefault("ZENML_ENABLE_REPO_INIT_WARNINGS", "false")
os.environ.setdefault("ZENML_CONFIG_PATH", str(Path(".zenml_local").resolve()))
os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
os.environ.setdefault("BENTOML_DO_NOT_TRACK", "true")

from mlops.retraining.config import load_retraining_config  # noqa: E402
from mlops.retraining.summary import (  # noqa: E402
    ROLLBACK_REQUIRED_FIELDS,
    SUMMARY_REQUIRED_FIELDS,
    validate_required_fields,
)

logger = logging.getLogger(__name__)


def _cmd_retrain(args: argparse.Namespace) -> int:
    cfg = load_retraining_config(mode=args.mode, tune=args.tune)
    # Imported lazily so the ZenML env vars above take effect first.
    from mlops.retraining.pipeline import run_retraining

    summary = run_retraining(cfg)
    print("Retraining complete.")
    print(f"  Mode:             {summary.get('pipeline_mode')}")
    print(f"  Status:           {summary.get('status')}")
    print(f"  Promoted:         {summary.get('promoted')}")
    print(f"  Primary metric:   {summary.get('primary_metric')}")
    print(f"  Candidate metric: {summary.get('candidate_metric')}")
    print(f"  Champion metric:  {summary.get('champion_metric')}")
    print(f"  Relative delta %: {summary.get('relative_delta_pct')}")
    print(f"  Rollback target:  {summary.get('rollback_target')}")
    if summary.get("rejected_reason"):
        print(f"  Rejected reason:  {summary['rejected_reason']}")
    if summary.get("failure_reason"):
        print(f"  Failure reason:   {summary['failure_reason']}")
    print(f"  Artifacts:        {cfg.artifacts_dir}")
    return 0 if summary.get("status") != "failed" else 1


def _cmd_check(args: argparse.Namespace) -> int:
    cfg = load_retraining_config(mode=args.mode)
    summary_path = cfg.artifacts_dir / "retraining_summary.json"
    rollback_path = cfg.artifacts_dir / "rollback_manifest.json"

    ok = True
    for path, required, label in (
        (summary_path, SUMMARY_REQUIRED_FIELDS, "retraining_summary.json"),
        (rollback_path, ROLLBACK_REQUIRED_FIELDS, "rollback_manifest.json"),
    ):
        if not path.exists():
            print(f"  MISSING: {label} (expected at {path})")
            ok = False
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        missing = validate_required_fields(payload, required)
        if missing:
            print(f"  INVALID: {label} missing fields: {missing}")
            ok = False
        else:
            print(f"  OK: {label} (schema_version={payload.get('schema_version')})")

    if ok:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        print("Retraining check passed.")
        print(f"  Status:   {summary.get('status')}")
        print(f"  Promoted: {summary.get('promoted')}")
        return 0
    print("Retraining check FAILED.")
    return 1


def _cmd_rollback(args: argparse.Namespace) -> int:
    cfg = load_retraining_config(mode=args.mode)
    from mlops.retraining.rollback import run_rollback

    report = run_rollback(cfg, confirm=args.confirm, reason=args.reason)
    print("Model rollback:")
    print(f"  Manifest:  {report.get('manifest_path')}")
    print(f"  Dry run:   {report.get('dry_run')}")
    print(f"  Valid:     {report.get('valid')}")
    print(f"  Executed:  {report.get('executed')}")
    for message in report.get("messages", []):
        print(f"    - {message}")
    if report.get("valid") is False:
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="InvForge PR-09 local retraining pipeline."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_retrain = sub.add_parser("retrain", help="Run the retraining pipeline.")
    p_retrain.add_argument("--mode", choices=("smoke", "full"), default=None)
    p_retrain.add_argument(
        "--tune",
        action="store_true",
        default=None,
        help="Enable bounded Optuna tuning (off by default).",
    )
    p_retrain.set_defaults(func=_cmd_retrain)

    p_check = sub.add_parser("check", help="Validate generated retraining artifacts.")
    p_check.add_argument("--mode", choices=("smoke", "full"), default=None)
    p_check.set_defaults(func=_cmd_check)

    p_rollback = sub.add_parser("rollback", help="Inspect/execute rollback.")
    p_rollback.add_argument("--mode", choices=("smoke", "full"), default=None)
    p_rollback.add_argument(
        "--confirm",
        action="store_true",
        help="Execute the rollback (otherwise dry run).",
    )
    p_rollback.add_argument(
        "--reason", default="manual rollback request", help="Rollback reason."
    )
    p_rollback.set_defaults(func=_cmd_rollback)
    return parser


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
