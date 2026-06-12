# Cloud dashboard demo fixtures

Lightweight, **committed synthetic artifacts** bundled into the Cloud Run
dashboard image so reviewers see a populated read-only UI without running the
local ML pipeline.

- **Source:** deterministic seed-42 pipeline output, truncated for size.
- **Scope:** dashboard visualization only — no models, no MLflow, no training.
- **Not production data.** Simulated backtest diagnostics only.

Regenerate locally (optional):

```bash
make demo-local
python scripts/export_dashboard_fixtures.py
```
