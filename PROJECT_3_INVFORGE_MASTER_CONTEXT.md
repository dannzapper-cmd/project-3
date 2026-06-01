# PROJECT 3 — InvForge · Master Context

> **Documento de referencia rápida.** Resumen denso y completo del proyecto para que cualquier IA o herramienta (Claude, ChatGPT, Cursor, v0) entienda en minutos qué se construye, con qué, por qué y en qué paso vamos. La documentación profunda vive en los documentos largos del proyecto; este es el mapa, no el territorio.

---

## Quick facts

| Campo | Valor |
|---|---|
| **Nombre** | InvForge — AI Operations Control Tower |
| **Tipo** | Capa AI/MLOps/DataOps/Security/Cloud sobre software empresarial open-source |
| **Software base** | InvenTree (MIT, Django/Python, REST API, plugin system, Docker oficial, activo 2026) |
| **Arquitectura** | Sidecar / AI Operations Layer externo (no se forkea ni se rompe el core) |
| **Dominio** | Inventario / operaciones / supply chain |
| **Rol objetivo** | Applied AI / ML Engineer / MLOps / AI Solutions / Forward Deployed |
| **Hardware local** | Laptop 8 GB RAM → Modo Local Lite + VM cloud puntual para cargas pesadas |
| **Filosofía de costo** | Free tiers + deploy barato apagable; VM por horas; clusters caros solo documentados |
| **Estado** | Diseño congelado. Siguiente paso = construir MVP de punta a punta. |

### Leyenda de clasificación de tecnologías

- **`[CORE]`** — Obligatorio en el MVP. Sin esto no hay proyecto.
- **`[REC]`** — Recomendado. Entra después del MVP, antes de Senior Edition.
- **`[SENIOR]`** — Senior Edition. **Implementado y corriendo**, no solo documentado.
- **`[DOC]`** — Solo documentación / ruta futura. No se implementa.
- **`[NO]`** — Anti-scope. Explícitamente fuera. Overengineering para este contexto.

---

## 1. Nombre del proyecto

**InvForge — AI Operations Control Tower for Inventory & Operations.**

## 2. Elevator pitch

InvForge toma InvenTree —un sistema de gestión de inventario open-source real— y le construye encima una capa externa de AI Operations que no modifica el sistema base. Esa capa añade demand forecasting, predicción de stockouts, anomaly detection, decision intelligence con operations research, y un loop completo de MLOps (feature store, tracking, drift, retraining, registry), todo observado, asegurado de forma defensiva, desplegado cloud-ready y reproducible. Demuestra una sola cosa: **sé tomar software empresarial existente y elevarlo a un sistema AI-ready production-like.**

## 3. Qué problema resuelve

Un sistema de inventario sabe qué tienes, pero no qué vas a necesitar. InvForge cierra ese hueco: predice demanda por item (incluyendo items de demanda intermitente), estima riesgo de stockout, calcula cuándo y cuánto reordenar con costos asimétricos reales, simula escenarios what-if, y monitorea la salud del sistema, los datos y el modelo. Convierte un sistema de registro en un sistema de decisión.

## 4. Por qué complementa LeadForge y SnapInsight

El portafolio queda redondo y sin repetición:

- **LeadForge** → agentic AI + B2B sales intelligence + producto + negocio + LLMOps.
- **SnapInsight** → multimodal AI + PWA mobile + product intelligence + GraphRAG/Neo4j + LLMOps.
- **InvForge** → ML clásico/deep learning puro + MLOps + data engineering + cloud/DevOps + ciberseguridad defensiva + enterprise systems.

Tesis transversal del portafolio: *"Puedo hacer IA productiva en cualquier contexto — consumer, enterprise, agentic, ML clásico, frontend, infraestructura."* InvForge cubre deliberadamente lo que los otros dos no tocan: **nada de agents, nada de multimodal**.

## 5. Qué hace el producto en la demo (90 segundos)

1. Abre InvenTree → datos reales de partes, stock, proveedores, movimientos (sintéticos pero realistas).
2. Cambia al **AI Operations Dashboard** (interfaz nueva, encima de InvenTree).
3. **Demand Forecast** por item: historial + predicción 30-90 días + prediction intervals.
4. **Stockout Risk Panel**: items en rojo/amarillo/verde con ROP y safety stock calculados.
5. **What-If Simulation**: demanda +25%, lead time mayor → recálculo en vivo + recomendación de reorden.
6. **MLflow**: experiment runs, champion vs baseline, MAE/RMSE/MAPE, SHAP values.
7. **Evidently**: reporte de drift / data quality.
8. **Grafana**: sistema (latencia, errores, uptime) + modelo (drift status, model version).
9. **Security Panel**: audit log, risk score, anomalía detectada en movimientos.

Cierre: número de impacto de negocio → *"reduje el costo simulado de inventario en X%"*.

## 6. Arquitectura general

```
[InvenTree Core]  ←→  [PostgreSQL principal]
        │ API REST (sin tocar el core)
        ▼
[AI Operations Layer]  (sidecar)
   ├── Ingestion Service        FastAPI ← consume API de InvenTree
   ├── Feature Pipeline         Feast + DuckDB + Polars
   ├── ML Training Pipeline     ZenML + MLflow + Optuna
   ├── Model Serving            BentoML + FastAPI
   ├── Monitoring               Evidently + Prometheus
   ├── Data Quality             Pandera / Great Expectations
   ├── Audit & Security         structured logging + risk scoring
   └── AI Operations Dashboard  Streamlit (MVP) → React/Next (prod)

[MLOps Stack]        MLflow 3 (tracking+registry) · Evidently · DVC · Feast
[Observability]      Prometheus · Grafana · OpenTelemetry  →  LGTM stack [SENIOR]
[Data Lineage]       OpenLineage + Marquez [SENIOR]
```

**Principio rector:** InvenTree corre en Docker Compose sin modificaciones. Toda la IA es externa y consume su API REST. Esto es lo más defendible en entrevista: integración limpia, no fork caótico.

## 7. Stack principal

| Capa | `[CORE]` | `[REC]` | `[SENIOR]` |
|---|---|---|---|
| Base | InvenTree, PostgreSQL, FastAPI, Docker Compose | — | — |
| Serving | FastAPI | BentoML (empaqueta el modelo principal) | BentoML en Kubernetes |
| Dashboard | Streamlit | React/Next | — |
| Dev tooling | uv, Ruff, pre-commit, mypy, detect-secrets, Bandit, Makefile/Justfile | GitHub Codespaces / devcontainer | — |
| CI/CD | GitHub Actions (build, test) | Trivy scan + badge, SBOM (Syft) | model signing Cosign/Sigstore (si aplica) |

## 8. Técnicas ML / forecasting

- **`[CORE]`** LightGBM / XGBoost (modelo global principal); Prophet / StatsForecast / Nixtla (forecasting); Isolation Forest (anomaly detection); SHAP (explainability).
- **`[CORE]`** **Croston / SBA** para items de demanda intermitente (clasificar items por ADI y CV², aplicar el método correcto a cada clase).
- **`[CORE]`** **Prediction intervals** (StatsForecast nativo o MAPIE) — nunca solo predicción puntual.
- **`[REC]`** Optuna (tuning); conformal prediction (intervalos con coverage garantizado); hierarchical forecasting con reconciliación (item ↔ categoría); walk-forward backtesting + test Diebold-Mariano (significancia estadística champion vs challenger).
- **`[SENIOR]`** **Time-series foundation models** (Chronos-2 / TimesFM) como benchmark: baseline estadístico → LightGBM global → foundation model zero-shot → foundation model fine-tuneado. Leaderboard con intervalos de confianza. Es el deep learning real, no decorativo. Zero-shot del modelo chico corre en CPU; fine-tuning en VM puntual.
- **`[SENIOR]`** TFT / N-BEATS como benchmark adicional → documentar resultado negativo si no le gana a LightGBM (honestidad técnica senior).

## 9. Decision intelligence

El loop que convierte predicción en acción (operations research clásico, lo que casi ningún portafolio tiene):

- **`[CORE]`** **Safety Stock** = Z × σ_demand × √lead_time
- **`[CORE]`** **Reorder Point (ROP)** = avg_demand × lead_time + safety_stock
- **`[CORE]`** **Economic Order Quantity (EOQ)** = √(2DS/H)
- **`[CORE]`** **Stockout probability** (clasificación: Isolation Forest / XGBoost)
- **`[CORE]`** **Cost-aware forecasting / quantile loss (pinball)**: el costo de faltante ≠ costo de sobrante (problema del newsvendor). Cuantil óptimo = Cu/(Cu+Co). LightGBM/StatsForecast soportan quantile objective nativo. → simular costo total (holding + stockout) sobre backtest vs baseline naive = **el número titular del proyecto**.
- **`[REC]`** **What-if simulation**: demanda, lead time, disponibilidad de proveedor → recálculo de recomendaciones.

## 10. MLOps / DataOps

- **`[CORE]`** MLflow 3 (experiment tracking + model registry + model signatures); Evidently (drift + data quality); model card + dataset card.
- **`[REC]`** ZenML (orquestación de pipelines como DAG, UI propia, integra MLflow+BentoML); champion/challenger; model rollback; retraining pipeline (manual + programado); W&B free tier (visualización de experimentos, opcional).
- **`[SENIOR]`** Retraining como Kubernetes CronJob; blue-green / canary model deployment; feature flags con Unleash; inference caching con Redis; graceful degradation con circuit breaker (fallback a baseline si el modelo no responde).

## 11. Data engineering

- **`[CORE]`** PostgreSQL; Feast (feature store — training/serving consistency, anti-leakage); Pandera o Great Expectations (data validation); DVC (data versioning simple); generador de datos sintéticos determinístico (SDV o Python+NumPy/Faker con estacionalidad, tendencia, ruido, demanda intermitente y stockouts simulados).
- **`[REC]`** dbt (transformaciones SQL documentadas + tests); Polars + DuckDB (análisis local eficiente); Prefect o Dagster (orquestación de datos — elegir uno).
- **`[SENIOR]`** OpenLineage + Marquez (lineage estándar, corriendo de verdad); OpenMetadata (data catalog); lakeFS (data version control enterprise — DVC fue adquirido por lakeFS en nov 2025; DVC sigue open-source para uso simple, lakeFS es la ruta enterprise).
- **`[DOC]`** Apache Iceberg / Delta Lake (lakehouse); BigQuery / Snowflake / Redshift (ruta enterprise).

## 12. Observabilidad

- **`[CORE]`** Health checks; structured logging; metrics endpoint; Prometheus + Grafana (dashboard de sistema + modelo); métricas: latencia, errores, data freshness, drift status, retraining status, model version.
- **`[REC]`** OpenTelemetry ligero (traces).
- **`[SENIOR]`** **Grafana LGTM stack completo**: Loki (logs) + Grafana (viz) + Tempo (traces) + Mimir (métricas), unificado por OpenTelemetry Collector. Correlación cross-signal (de un spike de métrica → traza → logs). **Prometheus AlertManager** con reglas reales (ej. "drift > threshold por 2 chequeos → alerta a webhook/Slack"). Detección → alerta → acción.

## 13. Ciberseguridad defensiva

Todo defensivo. Nada ofensivo, nada de hacking, nada de explotación.

- **`[CORE]`** Audit logs; secrets handling (env/Docker secrets); structured security logging.
- **`[REC]`** Risk scoring; anomaly detection en eventos/movimientos de inventario (Isolation Forest); RBAC básico; rate limiting; Trivy en CI/CD con badge ("0 critical"); SBOM con Syft como release artifact; dependency/secret scanning (Dependabot, detect-secrets, Bandit); security posture dashboard en UI.
- **`[SENIOR]`** **Defensive red-team / data poisoning simulation**: inyectar datos envenenados al training set → demostrar que Pandera/Great Expectations + Isolation Forest lo atrapan antes de contaminar el modelo → documentar como mini incident-response playbook (ataque → detección → contención → análisis). **Model signing con Cosign/Sigstore** (firmar el artefacto en CI, verificar firma antes del deploy en k8s = model provenance real).
- Estándares como checklist documentado: OWASP ML Security Top 10, NIST CSF 2.0 / AI RMF, threat model (STRIDE), EU AI Act considerations en model cards.

## 14. Cloud / multi-cloud / Kubernetes

Estrategia: **un cloud principal activo, dos perfiles documentados**.

- **`[CORE]`** Docker + Docker Compose (reproducible local).
- **`[REC]`** Deploy principal real barato: Google Cloud Run (pricing por request, se apaga sin tráfico) o Render / Fly.io. PostgreSQL gestionado: Neon / Supabase / Railway (free tiers). Perfiles `/deploy/gcp`, `/deploy/aws`, `/deploy/azure` — cada uno con README, método de deploy, variables, comando de teardown y cost notes. Docker image única reutilizable.
- **`[SENIOR]`** **Kubernetes con kind/k3s local** (un solo nodo, sin GPU, en 8 GB con resource limits). Workloads separados: API deployment (BentoML+FastAPI), worker (ingestion/feature materialization), batch (CronJob retraining), monitoring stack. Manifests limpios con resource limits/requests, liveness/readiness probes, ConfigMaps, Secrets, Ingress, RBAC, non-root containers. **Helm chart** para parametrizar. (InvenTree se queda en Docker Compose; solo la AI layer va a k8s.)
- **`[DOC]`** GKE / EKS / AKS (manifests y runbooks listos, sin clusters activos); Terraform (mención, sin infra real persistente); LocalStack (AWS sim); MinIO (S3-compatible local).

## 15. Senior Edition (implementada, no solo documentada)

Cuando alguien corre `make k8s-up`, levanta un cluster local con: AI Operations API, BentoML model server (deployment separado), CronJob de retraining, Feast Feature Server, ZenML runner, y el stack de observabilidad LGTM completo + AlertManager. Más: OpenLineage+Marquez corriendo, model signing verificado en el pipeline, blue-green model deployment, feature flags (Unleash), inference caching (Redis), graceful degradation, foundation models benchmarkeados, red-team de data poisoning demostrado, error analysis como entregable formal, resultados negativos documentados, y reproducibility checklist que de verdad funciona.

## 16. Qué NO debe hacerse — anti-scope `[NO]`

- Apache Spark (DuckDB+Polars resuelven el scope sin distribución).
- Kafka (no hay streaming real-time que lo justifique; batch es correcto).
- Kubeflow (demasiado pesado para el hardware y el scope).
- KServe / Seldon / Ray Serve (BentoML+FastAPI es suficiente y más fácil de demostrar).
- OPA Gatekeeper / Kyverno (policy-as-code: overkill aquí).
- Terraform completo (sin infra real persistente no aporta).
- Hopsworks u otro all-in-one (mejor entender cada pieza por separado).
- Modificar el core de InvenTree de forma caótica.
- Intentar correr todo local a la vez en 8 GB.
- Depender de APIs pagadas para el core.
- Ciberseguridad ofensiva de cualquier tipo.
- Dashboard bonito sin MLOps real detrás.
- README lleno de buzzwords sin demo que levante.
- Construir Senior Edition antes de tener el MVP desplegado de punta a punta.

## 17. Roadmap de 13 PRs

| PR | Nombre | Contenido |
|---|---|---|
| **PR-01** | Setup base | Docker Compose, InvenTree + PostgreSQL, estructura del repo, generador de datos sintéticos, skeleton de CI. |
| **PR-02** | Data pipeline | Ingestion Service, Feast feature pipeline, validación Pandera/Great Expectations, setup DVC. |
| **PR-03** | ML baseline | LightGBM/XGBoost + Prophet/StatsForecast, Croston/SBA para intermitente, SHAP, MLflow tracking, model card inicial. |
| **PR-04** | Decision intelligence | Safety stock, EOQ, reorder point, prediction intervals, stockout risk, cost-aware forecasting (quantile loss). |
| **PR-05** | MLOps loop | Evidently drift/data quality, model registry, champion/challenger, BentoML packaging. |
| **PR-06** | AI Operations Dashboard | Forecast viz, stockout risk panel, what-if simulation, model status, recomendaciones de decisión. |
| **PR-07** | Observability | Metrics endpoints, health checks, structured logs, OpenTelemetry, Prometheus/Grafana. |
| **PR-08** | Defensive security | Audit logs, risk scoring, inventory anomaly detection, Trivy, SBOM, secrets/security checks. |
| **PR-09** | Retraining pipeline | ZenML pipeline, Optuna tuning, model rollback, retraining programado/manual. |
| **PR-10** | Deploy + multi-cloud | Deploy principal (Google Cloud Run o equivalente) + perfiles `/deploy/gcp`, `/deploy/aws`, `/deploy/azure`. |
| **PR-11** | Senior Edition | Kubernetes kind/k3s, Helm/manifests, BentoML model server, CronJob retraining, LGTM/OpenLineage/Marquez si es viable, model signing, foundation models benchmark, red-team data poisoning. |
| **PR-12** | Full QA / audit | QA end-to-end, deploy check, model behavior check, MLOps check, security check, observability check, lista de gaps de docs, lista de bugfixes. |
| **PR-13** | Final packaging | README, case study, architecture diagram, ADRs, cost report, threat model, limitations, screenshots, script de video demo, narrativa de portafolio. |

**Orden no negociable:** MVP corriendo y desplegado real (PR-01 → PR-10) **antes** de Senior Edition (PR-11). Un sistema simple que funciona de punta a punta gana siempre a una Senior Edition a medias.

## 18. Qué debe verse en GitHub

README que abre con architecture diagram (Mermaid o imagen), demo GIF/video y badges (CI, Trivy "0 critical", coverage, Docker). Estructura de carpetas autoexplicativa:

```
/app            InvenTree config + docker-compose base
/api            FastAPI AI Operations API
/ml             modelos, features, training, /ml/notebooks (EDA + error_analysis)
/mlops          MLflow, Evidently, ZenML pipelines
/data           generación de datos sintéticos, DVC config
/feast          feature store definitions
/observability  Prometheus config, Grafana dashboards, LGTM
/security       audit logging, risk scoring, red-team playbook
/deploy         gcp/ aws/ azure/ k8s/(manifests + helm)
/docs           architecture/ model-cards/ adr/ costs/ runbooks/ case-study.md
.devcontainer   devcontainer.json (Open in Codespaces en 1 clic)
Makefile        make docker-up / train / serve / test / lint / k8s-up / generate-data
```

Docs obligatorios: architecture diagram, model card, dataset card, threat model (STRIDE), cost report (costo por modo), limitations/trade-offs, 3-5 ADRs ("por qué InvenTree y no frePPLe", "por qué sidecar y no fork", "por qué LightGBM y no TFT"), reproducibility checklist, case study escrito.

## 19. Qué debe verse en demo

Ver sección 5. La clave: en 90 segundos el espectador ve **sistema empresarial real + ML + MLOps + decision intelligence + observabilidad + seguridad**, todo conectado y corriendo. Que piense: *"esto no es un notebook, es un sistema."*

## 20. Narrativa de entrevista

> "Tomé InvenTree, un sistema de inventario open-source real, y construí encima una capa de AI Operations externa que no modifica el core. Añade demand forecasting con LightGBM y foundation models de series de tiempo, manejo de demanda intermitente con Croston/SBA, predicción de stockouts, y decision intelligence con safety stock, EOQ y reorder point optimizados con quantile loss porque los costos de faltante y sobrante son asimétricos — eso redujo el costo simulado de inventario en X%. Tiene un loop MLOps completo: feature store con Feast, tracking con MLflow 3, monitoreo con Evidently, retraining con ZenML. Todo observado con el stack LGTM de Grafana, asegurado con audit logs, risk scoring, anomaly detection y un ejercicio de red-team de data poisoning. El deploy principal está en Cloud Run, con perfiles para AWS y Azure y Kubernetes en Senior Edition, CI/CD con GitHub Actions, Trivy, SBOM y model signing. Cualquier pieza la puedo explicar porque la construí de verdad."

Diferenciador final: la mayoría sabe *qué herramientas existen*; muy pocos las conectan en un sistema coherente con criterio de producción y un número de impacto de negocio. Eso es lo que InvForge demuestra.
