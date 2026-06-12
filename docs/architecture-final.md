# InvForge — Final architecture overview

InvForge is an **external AI Operations sidecar** over [InvenTree](https://inventree.org/).
It adds forecasting, decision intelligence, MLOps, observability, and defensive
security **without modifying InvenTree core**.

## Sidecar principle

```mermaid
flowchart TB
    subgraph inventree ["InvenTree Base Stack (unchanged)"]
        PROXY["Caddy Proxy"]
        SERVER["InvenTree Server"]
        WORKER["Background Worker"]
        PG["PostgreSQL"]
        REDIS["Redis"]
    end

    subgraph invforge ["InvForge AI Operations Layer (external)"]
        API["FastAPI AI Ops API"]
        ML["ML Training / Serving"]
        MLOps["MLflow · Evidently · ZenML"]
        DASH["Streamlit Dashboard (local)"]
        OBS["Prometheus · Grafana"]
        SEC["Security Audit Pipeline"]
    end

    PROXY --> SERVER
    SERVER --> PG
    SERVER --> REDIS
    WORKER --> PG

    API -. "REST read-only (optional)" .-> SERVER
    ML --> API
    MLOps --> ML
    DASH -. "reads artifacts" .-> ML
    OBS -. "scrapes /metrics" .-> API
```

**Key constraint:** InvenTree runs in official Docker Compose images. InvForge
never patches the core. Integration is via REST API (optional) or synthetic data
(default demo path).

## Data flow

```mermaid
flowchart LR
    subgraph sources ["Data sources"]
        SYN["Synthetic generator\n(seed 42)"]
        IT["InvenTree REST API\n(optional)"]
    end

    subgraph pipeline ["Data pipeline"]
        RAW["Raw snapshots\ndata/raw/"]
        PROC["Processed CSVs\ndata/processed/"]
        VAL["Pandera validation"]
    end

    subgraph consume ["Consumers"]
        FEAST["Feast feature defs"]
        TRAIN["ML training"]
        API2["API /health summaries"]
    end

    SYN --> PROC
    IT --> RAW --> PROC
    PROC --> VAL
    VAL --> FEAST
    VAL --> TRAIN
    PROC --> API2
```

Default demo path uses **synthetic data only** — no live InvenTree required.

## Model flow

```mermaid
flowchart TB
    DATA["Validated demand history"]
    TRAIN["train-ml\nLightGBM + StatsForecast\nCroston/SBA"]
    DECIDE["decision-intel\nSafety stock · ROP · EOQ\nStockout risk"]
    MLOPS["mlops-loop\nEvidently · registry\nChampion/challenger · BentoML"]
    ART["artifacts/ + mlruns/"]
    DASH2["Dashboard (local)"]
    API3["API /health artifact checks"]

    DATA --> TRAIN --> DECIDE --> MLOPS --> ART
    ART --> DASH2
    ART --> API3
```

Forecast outputs include **p10/p50/p90 quantiles**, not point forecasts alone.
Decision intelligence converts quantiles into inventory policy recommendations.

## MLOps and retraining flow

```mermaid
flowchart LR
    LOOP["mlops-loop\n(local)"]
    RETRAIN["ZenML retraining DAG\n(local / kind Job)"]
    REG["MLflow registry"]
    PROMOTE["Gated promotion"]
    ROLL["Safe rollback"]
    LINE["OpenLineage → Marquez\n(optional kind profile)"]

    LOOP --> REG
    RETRAIN --> REG
    REG --> PROMOTE
    PROMOTE --> ROLL
    RETRAIN -. "optional emit" .-> LINE
```

Retraining is **local or kind Job evidence**, not a public cloud endpoint.

## Observability flow

```mermaid
flowchart TB
    API4["AI Ops API\n/health · /metrics"]
    PROM["Prometheus\n(local Docker or kind)"]
    GRAF["Grafana dashboards"]
    ALERT["AlertManager\n(kind profile)"]
    TEMPO["Tempo / OTel\n(idle until instrumented)"]

    API4 --> PROM --> GRAF
    PROM --> ALERT
    API4 -. "future traces" .-> TEMPO
```

PR-07 Docker stack: `make observability-up` (Grafana on port 3000).
PR-11B kind profile: full LGTM stack with alert webhook smoke test.

## Security boundary

```mermaid
flowchart TB
    subgraph public ["Public cloud surface (if activated)"]
        SAFE["GET /health\nGET /metrics\nGET /v1/inventory/status\nGET /v1/data/summary"]
    end

    subgraph blocked ["Blocked in demo/cloud mode"]
        MUT["POST /v1/ingest/inventree"]
        RET["Retrain / promote / rollback\n(not in deployable API)"]
    end

    subgraph local ["Local-only security pipeline"]
        AUDIT["security-audit"]
        SCAN["secrets-scan · bandit · pip-audit · trivy"]
    end

    MUT -->|"INVFORGE_ALLOW_MUTATIONS=false"| BLOCK["HTTP 403"]
```

No production auth layer on read-only routes. Mutation blocking is the hard
default for any public deployment.

## Local vs cloud boundary

| Layer | Local/dev | Cloud-deployable |
|-------|-----------|------------------|
| AI Operations API | `make observability-api` | Docker image → Cloud Run / ECS / Container Apps |
| Dashboard | `make dashboard` | Not deployed |
| MLflow/ZenML | Local `mlruns/`, ZenML stack | Not deployed |
| InvenTree | `make docker-up` | External — not part of InvForge deploy |
| kind k8s profiles | `make k8s-up`, `obs-k8s-up`, `lineage-up` | Local kind only |
| Observability Docker | `make observability-up` | Local/dev only |

See [deployment contract](deployment-contract.md) for endpoint classification.

## Kubernetes local profiles

PR-11A deploys **only the AI Operations Layer** to kind:

- Chart: `deploy/k8s/helm/invforge`
- Image: `invforge-ai-ops:local`
- Namespace: `invforge-ai`

PR-11B adds **optional** profiles (never auto-started):

- Observability: `deploy/k8s/observability` → Prometheus, Grafana, Loki, Tempo, AlertManager
- Lineage: `deploy/k8s/lineage` → Marquez + OpenLineage

These prove architecture and smoke tests; they are **not** managed cloud Kubernetes.

## Cloud deployable surface

The repo-root `Dockerfile` builds a single container with the FastAPI sidecar.
Deploy profiles:

| Provider | Target | Guide |
|----------|--------|-------|
| GCP (primary) | Cloud Run | [GCP activation](cloud/gcp-cloud-run-activation.md) |
| AWS | ECS Fargate | [AWS activation](cloud/aws-ecs-fargate-activation.md) |
| Azure | Container Apps | [Azure activation](cloud/azure-container-apps-activation.md) |

**Status:** templates only. No live cloud resources in CI or PR-13.

## Related documents

- [Deployment contract](deployment-contract.md)
- [Backend and ML explainer](tutorials/backend-and-ml-explainer.md)
- [Limitations](limitations.md)
- [Observability](observability.md)
- [MLOps](mlops.md)
- [Decision intelligence](decision-intelligence.md)
