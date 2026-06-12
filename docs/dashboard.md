# AI Operations Dashboard (PR-06)

PR-06 adds a **local Streamlit + Plotly dashboard** that visualizes existing
artifacts from PR-03 (ML forecasting / MLflow), PR-04 (decision intelligence),
and PR-05 (MLOps loop). It is read-only: it does **not** train models, recompute
metrics, or trigger pipelines.

## Generate artifacts first

Run these in order (same as prior PRs):

```bash
make UV="uv" generate-data
make UV="uv" train-ml
make UV="uv" decision-intel
make UV="uv" mlops-loop
```

Optional dependency install:

```bash
uv sync --group dev --group ml --group mlops --group dashboard
```

## Cloud demo mode (PR-15)

The dashboard can deploy read-only to Cloud Run via `Dockerfile.dashboard`:

- Bundled fixtures: `dashboard/demo_fixtures/` (~116 KB, synthetic seed 42)
- Reviewer login gate: `INVFORGE_DEMO_AUTH_ENABLED`, `INVFORGE_DEMO_USER`, `INVFORGE_DEMO_PASSWORD`
- Live URL: see README **Try InvForge** section

Local mode unchanged — reads workspace artifacts from `make reviewer-demo`.

## Launch the dashboard

```bash
make UV="uv" dashboard
```

Equivalent:

```bash
uv run --group dashboard streamlit run dashboard/app.py
```

Open the URL printed by Streamlit (typically `http://localhost:8501`).

## Non-interactive smoke check

Validates loader import/call contracts without a browser:

```bash
make UV="uv" dashboard-smoke
```

## Dashboard sections

| Section | What it shows | Primary artifacts |
|---------|---------------|-------------------|
| **1. Overview** | Status cards for data, ML forecast, decision, MLOps | Synthetic CSV markers; presence of downstream JSON |
| **2. Forecast Performance** | LightGBM vs StatsForecast MAE/RMSE/MAPE; champion/challenger decision | `artifacts/mlops/champion_challenger/comparison.json` |
| **3. Decision Intelligence** | Top reorder recommendations; safety stock, ROP, EOQ, stockout risk; simulated cost assumptions | `artifacts/decision/decision_summary.json`, `artifacts/decision/decision_recommendations.csv` |
| **4. MLOps Status** | Drift flag, registry strategy, BentoML packaging, Evidently report presence | `artifacts/mlops/mlops_loop_summary.json`, `registry/registered_model_summary.json`, `bentoml/build_summary.json`, `evidently/*.json` |
| **5. Limitations** | Synthetic-data disclaimer; deferred PR-07/10/11 scope | Static copy |

Each section that loads a file successfully shows **Last generated: YYYY-MM-DD HH:MM**
from the artifact file's filesystem mtime.

## Missing artifacts

If a section shows **Status: missing**, the dashboard explains which file is
absent and lists the exact `make` commands to generate it. The UI does not crash
and does not invent placeholder metrics.

## Warnings and scope

- All data is **synthetic** (seed 42). No real InvenTree inventory is used.
- Cost reductions and policy improvements are **simulated backtest diagnostics**;
  **no real-world savings claims** are made or implied.
- This is a **local dashboard only**, not production monitoring or alerting.
- **Grafana, Prometheus, OpenTelemetry** → PR-07.
- **Cloud deploy profiles** → PR-10.
- **Kubernetes / Helm** → PR-11.

## Implementation layout

```
dashboard/
  app.py       Streamlit UI (read-only)
  loaders.py   Typed artifact loaders
  smoke.py     Non-interactive contract checks
  paths.py     Default artifact paths
```

Generated `artifacts/` and `mlruns/` remain git-ignored.
