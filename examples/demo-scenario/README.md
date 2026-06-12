# Demo scenario — mixed-demand inventory review

This scenario gives reviewers a **concrete story** to follow while running the
local pipeline. It uses synthetic SKUs from `data/synthetic/generate_inventory_data.py`
(seed 42). No private data is included.

## Situation

Acme Parts Co. operates a small warehouse. Operations wants to know which SKUs
need attention this week: steady movers, intermittent spare parts, and items at
stockout risk given supplier lead times.

## SKUs in the scenario

See `demo_scenario.yaml` for structured fields. Summary:

| SKU | Demand pattern | Lead time | Story |
|-----|----------------|-----------|-------|
| `SKU-A100` | Regular weekly demand | 7 days | Stable fast mover — forecast MAE drives reorder point |
| `SKU-B220` | Intermittent / lumpy | 14 days | Spare part — Croston/SBA style forecast matters |
| `SKU-C330` | Regular, rising trend | 10 days | Approaching stockout if no reorder |
| `SKU-D440` | Low volume | 21 days | Long lead time — safety stock dominates |

## Expected dashboard interpretation

After `make demo-local` (or the manual pipeline) and `make dashboard`:

1. **Overview** — all four artifact families should show present (data, ML, decision, MLOps).
2. **Forecast performance** — compare LightGBM vs StatsForecast; champion/challenger JSON shows the winner.
3. **Decision intelligence** — `SKU-C330` and `SKU-D440` should rank among higher stockout-risk items; `SKU-A100` should show a clear reorder recommendation.
4. **MLOps status** — drift flag and registry strategy from the latest loop run.

## Expected business decision

Operations would:

- **Reorder `SKU-C330`** soon (stockout risk + lead time).
- **Increase safety stock for `SKU-D440`** given 21-day supplier lead time.
- **Keep `SKU-A100` on a standard ROP** with weekly review.
- **Treat `SKU-B220` as intermittent** — avoid over-ordering from naive averages.

## What-if example

"If supplier lead time for `SKU-D440` increases from 21 to 28 days, safety stock
should rise and the reorder point moves earlier." The decision layer encodes this
via lead-time inputs in the synthetic generator; re-run `make decision-intel` after
changing generator config locally (not required for the default demo).

## API checks

With `make observability-api` running:

```bash
curl -s http://localhost:8001/health | jq .status,.artifacts
curl -s http://localhost:8001/v1/inventory/status | jq .status,.demo_mode
```

Sample JSON shapes: `examples/api/sample_health_response.json`,
`examples/api/sample_inventory_status_response.json`.

## Commands

```bash
make demo-local
make dashboard          # interactive
make dashboard-smoke    # non-interactive
```

## Honest scope

- All numbers are **synthetic backtest diagnostics**.
- No real InvenTree instance is required for this scenario.
- Do not cite dollar savings from this demo.
