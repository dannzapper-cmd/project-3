# PR-02 Runbook — Data Pipeline Foundation

This runbook covers the InvForge PR-02 data pipeline foundation. InvForge remains an external AI Operations sidecar: it does not modify, fork, vendor, or patch InvenTree core code.

## Components added

- FastAPI AI Operations API under `api/`
- Async, read-only InvenTree REST client using `httpx`
- Ingestion pipeline for documented InvenTree resources:
  - parts/items: `/api/part/`
  - stock records: `/api/stock/`
  - categories: `/api/part/category/`
  - companies/suppliers: `/api/company/`
- Raw snapshots under `data/raw/inventree/`
- Processed CSV tables under `data/processed/`
- Pandera validation for synthetic and processed CSVs
- DVC metadata and local `generate-data` / `validate-data` stages
- Minimal Feast feature repo skeleton under `feast/`

## Environment variables

Copy the safe placeholder file if desired:

```bash
cp api/.env.example api/.env
```

Live ingestion supports two authentication options. Token auth remains the preferred production-like option. Basic Auth is a local-development fallback for Docker Desktop smoke tests when local token generation is not working.

Option A — token auth:

```bash
export INVENTREE_BASE_URL=http://inventree.localhost:8080
export INVENTREE_API_TOKEN=<real-token>
unset INVENTREE_USERNAME INVENTREE_PASSWORD
```

Option B — local Basic Auth fallback:

```bash
export INVENTREE_BASE_URL=http://inventree.localhost:8080
export INVENTREE_API_TOKEN=replace-me
export INVENTREE_USERNAME=admin
export INVENTREE_PASSWORD=<local-admin-password>
```

If `INVENTREE_API_TOKEN` is set to a real value, token auth is used. Basic Auth is only used when the token is unset or left as `replace-me` and both username and password are configured. The placeholder password `replace-me-local-only` is treated as not configured.

Optional:

```bash
export INVFORGE_DATA_DIR=data
export INVFORGE_API_PORT=8001
export INVENTREE_TIMEOUT_SECONDS=10
```

Do not commit real tokens, usernames tied to real systems, or passwords.

## Setup

Install dependencies through `pyproject.toml` only:

```bash
uv sync --group dev --group pipeline
```

The `pipeline` group contains DVC and Feast. Feast is not a core runtime dependency and no Feast server is started in PR-02.

## Local commands

Generate deterministic synthetic data:

```bash
make generate-data
```

Validate generated synthetic data and any processed ingestion outputs:

```bash
make validate-data
```

Reproduce the DVC pipeline:

```bash
make dvc-repro
```

Run tests and lint:

```bash
uv run ruff check .
uv run pytest
```

Run the FastAPI sidecar:

```bash
make api-dev
```

Check health:

```bash
make api-health
```

## Local live ingestion smoke

Live ingestion requires a running InvenTree stack and valid credentials. It should fail clearly if InvenTree is unavailable or credentials are missing.

Token auth smoke:

```bash
make docker-up
make api-dev
export INVENTREE_BASE_URL=http://inventree.localhost:8080
export INVENTREE_API_TOKEN=<real-token>
unset INVENTREE_USERNAME INVENTREE_PASSWORD
make ingest-inventree
```

Local Basic Auth fallback smoke:

```bash
make docker-up
make api-dev
export INVENTREE_BASE_URL=http://inventree.localhost:8080
export INVENTREE_API_TOKEN=replace-me
export INVENTREE_USERNAME=admin
export INVENTREE_PASSWORD=<local-admin-password>
make ingest-inventree
```

Successful ingestion writes:

- raw JSONL snapshots: `data/raw/inventree/<timestamp>/*.jsonl`
- normalized CSVs: `data/processed/*.csv`

These output folders are gitignored.

## API endpoints

- `GET /health`
- `GET /v1/inventory/status`
- `POST /v1/ingest/inventree`
- `GET /v1/data/summary`

Logs are structured JSON via `structlog` with `timestamp`, `level`, `service`, and `message` fields. Token, username, and password values are not included in API errors or logs.

## Validation coverage

Pandera catches:

- missing required columns
- negative lead times
- invalid dates
- negative demand or stock quantities
- invalid categorical flags such as `stockout_flag`

Processed InvenTree CSV validation is optional when `data/processed/` does not exist, so local synthetic validation and DVC reproduction work without a live InvenTree instance.

## Known limitations

- PR-02 only reads from InvenTree; it does not seed or write data into InvenTree.
- Endpoint schemas are normalized conservatively from documented REST resources. Local `/api-doc/` should be used when adapting to a different InvenTree version.
- No ML models, MLflow, Evidently, dashboards, Grafana/Prometheus, BentoML, Kubernetes, cloud deploy, or security scanning features are implemented in PR-02.
- Feast is a minimal repo skeleton only; no materialization or feature server is started.
- If Docker or live InvenTree credentials are unavailable, do not claim live ingestion works. Use mocked tests plus local synthetic validation instead.

