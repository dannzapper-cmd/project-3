# Runbook — Data lineage inspection (PR-11B)

InvForge emits OpenLineage events from the retraining pipeline to a local
Marquez. Lineage is an **optional** profile, separate from observability, in its
own namespace (`invforge-lineage`). Local/dev only; ephemeral DB; no secrets.

## What is implemented

- **OpenLineage emission** (`mlops/retraining/lineage.py`): a small, env-gated
  wrapper. `run_retraining` emits real `START`/`COMPLETE`/`FAIL` run events for
  the `invforge.retraining` job. It is a **no-op unless `OPENLINEAGE_URL` is
  set**, so the default `make retrain-smoke` and CI are unchanged. Emission is
  **unit-validated** (`ml/tests/test_retraining_lineage.py` captures real
  `RunEvent` objects).
- **Marquez deployment** (`deploy/k8s/lineage`): Marquez API + web + an embedded
  ephemeral PostgreSQL, with `make lineage-*` targets.

End-to-end Marquez UI inspection requires Docker/kind and is the local step
below.

## Bring up Marquez

```bash
# One heavy profile at a time. If observability is up and RAM is tight,
# `make obs-k8s-down` first.
make lineage-up
make lineage-status            # wait until marquez-db, marquez-api, marquez-web are Running
make lineage-port-forward      # marquez-web:3000, marquez-api:5000
```

Marquez UI: http://localhost:3000 — Marquez API: http://localhost:5000

## Emit a real event and verify

```bash
make lineage-smoke
```

This runs `deploy/k8s/lineage/scripts/smoke.sh`, which:

1. checks the Marquez API is reachable at `http://localhost:5000`;
2. runs `OPENLINEAGE_URL=http://localhost:5000 make retrain-smoke` (a real,
   deterministic retraining run that emits START + COMPLETE);
3. queries `GET /api/v1/namespaces/invforge/jobs` and asserts the
   `invforge.retraining` job appears.

Then in the UI you can browse the `invforge` namespace → `invforge.retraining`
job → its runs.

Manual equivalent:

```bash
export OPENLINEAGE_URL=http://localhost:5000
make retrain-smoke
curl -s http://localhost:5000/api/v1/namespaces/invforge/jobs | head
```

## Tear down

```bash
make lineage-down
```

## Scope / honesty notes

- Lineage events are emitted **directly via the OpenLineage Python client**, not
  through a ZenML server (the pipeline runs local/offline). This is the correct
  path for this architecture.
- Marquez uses an **ephemeral embedded PostgreSQL** (data lost on restart) — it
  is a dev profile, not a persistent catalog. A PVC would be a production step.
- **OpenMetadata is intentionally excluded** (heavy metadata platform; see
  ADR 003).
