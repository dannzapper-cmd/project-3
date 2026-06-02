# MLOps Loop (PR-05)

InvForge PR-05 adds a **minimal, local, deterministic, offline** MLOps loop on
top of the PR-03 forecasting baseline and PR-04 decision intelligence. It is a
monitoring + packaging layer, not a serving platform. Everything runs on your
machine with no external APIs, cloud services, or paid dependencies.

## What it does

`make mlops-loop` runs four steps and writes lightweight artifacts under
`artifacts/mlops/`:

1. **Evidently drift + data quality reports** on a temporal reference/current
   split of the engineered feature table.
2. **MLflow model registry / metadata** for the current demand forecasting
   model (champion).
3. **Champion/challenger comparison** built only from existing PR-03/PR-04
   metric artifacts.
4. **Minimal BentoML packaging** of the champion model into the local model
   store (no Docker, no serving deployment, no Kubernetes).

It is **idempotent**: rerunning it overwrites the deterministic JSON/HTML
reports and deduplicates registry/BentoML entries by source run id, so it never
corrupts artifacts.

## How to run

```bash
# 1. Generate synthetic data (deterministic, seed 42)
make generate-data

# 2. Train PR-03 baseline (populates the local mlruns/ store + champion model)
make train-ml

# 3. (Optional but recommended) PR-04 decision intelligence for cost context
make decision-intel

# 4. Run the PR-05 MLOps loop
make mlops-loop
```

The loop degrades gracefully: if `make train-ml` has not been run, there is no
champion model in `mlruns/`, so the registry step falls back to a JSON-only
summary, the champion/challenger decision becomes `manual_review`, and BentoML
packaging reports `skipped`. The Evidently reports only need the synthetic data
and are always produced.

Dependencies for the loop live in the optional `mlops` uv group
(`evidently`, `bentoml`). The Makefile target installs them via
`uv run --group ml --group mlops`.

## Artifacts and what they mean

All outputs are written under `artifacts/mlops/` (git-ignored — see
[Artifact hygiene](#artifact-hygiene)).

| Path | Meaning |
|------|---------|
| `evidently/data_drift_report.html` / `.json` | Evidently data drift report (reference vs current). |
| `evidently/data_quality_report.html` / `.json` | Evidently data summary/quality report. |
| `registry/registered_model_summary.json` | MLflow registry metadata for the champion (version, alias, tags, params, metrics, artifact refs, signature info). |
| `champion_challenger/comparison.json` | Deterministic champion vs challenger comparison + decision. |
| `champion_challenger/comparison.md` | Human-readable version of the comparison. |
| `bentoml/build_summary.json` | BentoML packaging result (`packaged`, `skipped`, `deferred`, or `disabled`). |
| `mlops_loop_summary.json` | Top-level aggregated status for all four steps (stable schema for the PR-06 dashboard). |

### Stable JSON schemas

Each JSON output carries a `schema_version` field and a `warnings` /
`limitations` block so the future PR-06 dashboard can consume them safely. The
drift report additionally exposes a compact, parsed `drift_summary`:

```json
{
  "dataset_drift_detected": false,
  "drifted_columns_count": 2,
  "drifted_share": 0.18,
  "drift_share_threshold": 0.5,
  "columns": [{"column": "lag_7", "method": "K-S p_value",
               "threshold": 0.05, "score": 0.4, "drifted": false}]
}
```

## Temporal reference/current split (no leakage)

Drift monitoring uses a **strict temporal boundary split**, never a random
sample:

- **Reference** = rows on the first `reference_fraction` (default `0.80`) of
  distinct sorted dates in `demand_history.csv`.
- **Current** = rows on the remaining (most recent) dates.

The split validates that no current-period date appears in the reference window
(`reference_max_date < current_min_date`). If the feature columns configured for
drift are missing, the loop **fails with a clear error** instead of silently
producing nonsense.

## Drift configuration / thresholds

Configured in [`mlops/config.yaml`](../mlops/config.yaml) under `evidently`:

| Key | Default | Meaning |
|-----|---------|---------|
| `reference_fraction` | `0.80` | Fraction of earliest dates used as the reference window. |
| `drift_share_threshold` | `0.5` | Dataset-level drift is flagged when the share of drifted columns meets/exceeds this. |
| `per_column_pvalue_threshold` | `0.05` | Documented per-column significance threshold (Evidently selects the test per column type). |
| `numerical_columns` / `categorical_columns` | feature lists | Columns analysed for drift/quality. |

## Champion/challenger comparison

- **Champion** = the current/primary demand forecasting model (global
  **LightGBM**). **Challenger** = the **StatsForecast** statistical baseline.
- Both models come from the **same PR-03 temporal split**, so the comparison is
  apples-to-apples.
- **Primary metric: `mae`** (lower is better). `rmse` and `mape` are reported as
  context.
- Metrics are read **only** from the existing PR-03 MLflow run and the PR-04
  `decision_summary.json`. Nothing is recomputed from raw data; no training or
  backtesting is re-run; PR-03/PR-04 metric files are never mutated.
- **Decision** is one of:
  - `promote_challenger` — challenger improves the primary metric by at least
    `decision_threshold_pct` (default 5%).
  - `keep_champion` — champion is better by at least the threshold.
  - `manual_review` — models are within the threshold (too close to call) **or**
    metrics are missing/incomplete. We choose `manual_review` rather than
    forcing a winner.
- On the current synthetic baseline (LightGBM MAE ≈ 2.11 vs StatsForecast MAE
  ≈ 2.09) the models are within ~1.2%, so the honest decision is
  `manual_review`.
- Synthetic cost figures from PR-04 are included only as **labelled
  synthetic/simulated** supporting context. They are never presented as
  real-world savings.

## MLflow registry strategy

**Chosen strategy: native MLflow Model Registry with aliases**
(`registry_strategy = "native_aliases"`). MLflow 3.x can register models and
assign the `champion` alias against the local file-store `mlruns/` directory,
with no additional running service.

The loop tags each registered version (`scope=pr05`, `data_source=synthetic`,
`production_ready=false`, plus a `pr05_champion_run_id` tag) and points the
`champion` alias at it. Registration is **idempotent**: if a version already
maps to the same source run id, it is reused instead of creating a duplicate.

If native registration cannot proceed (e.g. no trained run exists yet, or a
registry call fails), the loop **falls back** to
`registry_strategy = "tags_json_fallback"` and writes a JSON-only summary that
records why.

### Local registry limitations (honest)

- Local file-store registry only: **no central server, authentication, stage
  transition audit, or multi-user governance**.
- The `mlruns/` store is regenerated locally and is **not committed to git**, so
  registry state is **ephemeral per machine**.
- Models are trained on **synthetic** data; registry metadata does not imply
  production readiness.

## BentoML packaging

PR-05 performs **minimal** BentoML packaging only: it loads the champion
LightGBM model from MLflow and saves it into the **local BentoML model store**
(`~/bentoml`, outside the repo) with a model signature, labels, and metadata.

It does **not** run `bentoml build`, build a Docker image, deploy a service,
use BentoCloud, or touch Kubernetes. A minimal, illustrative serving scaffold
lives in [`mlops/service.py`](../mlops/service.py) for manual local use only:

```bash
uv run --group ml --group mlops bentoml serve mlops.service:DemandForecastService
```

Packaging is idempotent (deduplicated by `mlflow_run_id` label) and degrades to
`skipped`/`deferred` (recorded in `bentoml/build_summary.json`) if no champion
model is available or BentoML is unavailable.

### BentoML Deferral

BentoML was evaluated against the pinned environment and resolved cleanly with
**no dependency conflicts**, so packaging is implemented (not deferred). Should
BentoML ever introduce a dependency conflict in a future environment, PR-05 will
**not** mutate `pyproject.toml`/`uv.lock` to force it; instead the loop writes
`bentoml/build_summary.json` with `status: deferred` and
`deferred_to: "PR-10 or PR-11"` (serving/deployment belongs to the deploy and
Kubernetes/Senior Edition PRs) and continues normally.

## Artifact hygiene

The entire `artifacts/` tree (including `artifacts/mlops/`) is git-ignored, as
are `mlruns/` and the BentoML store (`bentoml/`, `.bentoml/`, `*.bento`). PR-05
commits **code, tests, docs, configs, and this documentation only** — never
generated model binaries, large Evidently HTML reports, Bento build directories,
or MLflow run directories.

## Why Kubernetes is intentionally deferred

PR-05 is deliberately scoped to **local MLOps packaging and monitoring**:
offline Evidently reports, a local MLflow registry, a deterministic
champion/challenger comparison, and local BentoML model packaging. It runs on a
laptop with no cluster, no service mesh, and no cloud account.

Kubernetes-based concerns — k8s/k3s manifests, Helm charts, model serving in a
cluster, autoscaling, and production rollout/canary infrastructure — are
**intentionally deferred to PR-11 (Senior Edition)**, with serving/deployment
packaging covered by PR-10. Pulling that infrastructure into PR-05 would add
heavy operational surface area (clusters, ingress, secrets management, image
registries) that contradicts PR-05's "local, deterministic, lightweight,
offline" goal and would overlap the later deployment PRs. Keeping the boundary
crisp lets PR-05 stay reviewable and reproducible while leaving real serving and
orchestration to the PRs designed for it.

## Limitations summary

- **Synthetic data only** (seed 42); nothing here reflects live InvenTree
  demand.
- Drift, champion/challenger, and cost figures are **synthetic/simulated**
  diagnostics, not real-world performance or savings claims.
- The local MLflow registry and BentoML store are **ephemeral** and
  single-machine.
- This is a monitoring/packaging loop, **not** a monitoring service, dashboard,
  alerting system, or production deployment.
