# InvForge Makefile
# Common development and CI commands for InvForge.

UV ?= uv
COMPOSE_FILE := app/docker-compose.yml
COMPOSE_ENV := app/.env
COMPOSE := docker compose -f $(COMPOSE_FILE) --env-file $(COMPOSE_ENV)
OBSERVABILITY_COMPOSE := observability/docker-compose.observability.yml
OUTPUT_DIR := data/synthetic/output
SEED := 42
INVFORGE_API_PORT ?= 8001
# PR-10 deploy image + smoke defaults.
AI_IMAGE ?= invforge-ai-ops:local
BASE_URL ?= http://localhost:$(INVFORGE_API_PORT)

.PHONY: help docker-config docker-up docker-down docker-logs docker-init api-dev api-health ingest-inventree generate-data validate-data dvc-repro train-ml decision-intel mlops-loop dashboard dashboard-smoke observability-api observability-up observability-down observability-smoke security-audit security-smoke security-check trivy-scan sbom deploy-validate deploy-smoke docker-build-ai docker-smoke lint test secrets-scan ci

help:
	@echo "InvForge — available targets:"
	@echo "  docker-config   Validate Docker Compose configuration"
	@echo "  docker-up       Start InvenTree base stack"
	@echo "  docker-down     Stop InvenTree base stack"
	@echo "  docker-logs     Tail InvenTree stack logs"
	@echo "  docker-init     Run first-time InvenTree DB/static setup (invoke update)"
	@echo "  api-dev         Start the InvForge FastAPI sidecar"
	@echo "  api-health      Check the InvForge API health endpoint"
	@echo "  ingest-inventree Trigger read-only InvenTree ingestion via the API"
	@echo "  generate-data   Generate deterministic synthetic inventory CSVs"
	@echo "  validate-data   Validate synthetic and processed data with Pandera"
	@echo "  dvc-repro       Reproduce the DVC data pipeline"
	@echo "  train-ml        Train PR-03 demand forecast baselines"
	@echo "  decision-intel  Generate PR-04 inventory recommendations"
	@echo "  mlops-loop      Run PR-05 local MLOps loop"
	@echo "  dashboard       Launch PR-06 Streamlit AI Operations dashboard"
	@echo "  dashboard-smoke Non-interactive dashboard loader smoke check"
	@echo "  observability-api   Start the AI Ops API with /health and /metrics (uvicorn)"
	@echo "  observability-up    Start local Prometheus + Grafana (Docker)"
	@echo "  observability-down  Stop local Prometheus + Grafana (Docker)"
	@echo "  observability-smoke Offline observability health/metrics smoke check"
	@echo "  security-audit    Run PR-08 defensive security pipeline (artifacts)"
	@echo "  security-smoke    Validate generated security artifacts (offline)"
	@echo "  security-check    Bandit + pip-audit + detect-secrets"
	@echo "  trivy-scan        Filesystem scan (CRITICAL blocks, HIGH reports)"
	@echo "  sbom              Generate CycloneDX SBOM (requires syft)"
	@echo "  deploy-validate   Validate PR-10 deploy profiles/templates (offline)"
	@echo "  deploy-smoke      Read-only smoke check (BASE_URL=...) against a running API"
	@echo "  docker-build-ai   Build the deployable AI Operations Layer image"
	@echo "  docker-smoke      Build+run AI Ops container (demo mode) and smoke it"
	@echo "  lint            Run Ruff linter"
	@echo "  test            Run pytest"
	@echo "  secrets-scan    Scan repository for secrets"
	@echo "  ci              Run local CI checks"

docker-config:
	@test -f $(COMPOSE_ENV) || cp app/.env.example $(COMPOSE_ENV)
	@if command -v docker >/dev/null 2>&1; then \
		$(COMPOSE) config; \
	else \
		echo "WARNING: docker not available; skipping compose config validation"; \
	fi

docker-up:
	@test -f $(COMPOSE_ENV) || cp app/.env.example $(COMPOSE_ENV)
	$(COMPOSE) up -d

docker-down:
	@test -f $(COMPOSE_ENV) || cp app/.env.example $(COMPOSE_ENV)
	$(COMPOSE) down

docker-logs:
	@test -f $(COMPOSE_ENV) || cp app/.env.example $(COMPOSE_ENV)
	$(COMPOSE) logs -f

docker-init:
	@test -f $(COMPOSE_ENV) || cp app/.env.example $(COMPOSE_ENV)
	@echo "Running InvenTree first-time setup (invoke update)..."
	$(COMPOSE) run --rm -T inventree-server invoke update

api-dev:
	INVFORGE_API_PORT=$(INVFORGE_API_PORT) $(UV) run uvicorn api.main:app --host 0.0.0.0 --port $(INVFORGE_API_PORT) --reload

api-health:
	curl --fail http://localhost:$(INVFORGE_API_PORT)/health

ingest-inventree:
	curl --fail -X POST http://localhost:$(INVFORGE_API_PORT)/v1/ingest/inventree

generate-data:
	$(UV) run python data/synthetic/generate_inventory_data.py --output $(OUTPUT_DIR) --seed $(SEED)

validate-data:
	$(UV) run python -m api.validation --synthetic-dir $(OUTPUT_DIR) --processed-dir data/processed

dvc-repro:
	$(UV) run dvc repro

train-ml: generate-data
	MLFLOW_TRACKING_URI=mlruns MLFLOW_ALLOW_FILE_STORE=true $(UV) run --group ml python -m ml.train --config ml/config.yaml

decision-intel: generate-data
	MLFLOW_TRACKING_URI=mlruns MLFLOW_ALLOW_FILE_STORE=true $(UV) run --group ml python -m ml.decision_intelligence --config ml/config.yaml

# PR-05 local MLOps loop: Evidently drift/quality reports, MLflow registry
# metadata, champion/challenger comparison, and minimal BentoML packaging.
# Idempotent and offline. Run train-ml (and optionally decision-intel) first so
# the champion model and PR-04 cost context are available.
mlops-loop: generate-data
	MLFLOW_TRACKING_URI=mlruns MLFLOW_ALLOW_FILE_STORE=true BENTOML_DO_NOT_TRACK=true $(UV) run --group ml --group mlops python -m mlops.loop --config mlops/config.yaml --ml-config ml/config.yaml

# PR-09 local retraining pipeline (ZenML local DAG + Optuna + safe rollback).
# Smoke mode is deterministic and fast (small subset, no tuning) and does NOT
# require BentoML or a running server. Generates synthetic data first so the
# pipeline is self-contained.
RETRAIN_ENV := MLFLOW_TRACKING_URI=mlruns MLFLOW_ALLOW_FILE_STORE=true BENTOML_DO_NOT_TRACK=true ZENML_ANALYTICS_OPT_IN=false

retrain-smoke: generate-data
	$(RETRAIN_ENV) RETRAINING_MODE=smoke $(UV) run --group ml --group retraining python -m mlops.retraining.runner retrain --mode smoke

retrain: generate-data
	$(RETRAIN_ENV) RETRAINING_MODE=full $(UV) run --group ml --group retraining python -m mlops.retraining.runner retrain --mode full

retrain-tune: generate-data
	$(RETRAIN_ENV) RETRAINING_MODE=smoke $(UV) run --group ml --group retraining python -m mlops.retraining.runner retrain --mode smoke --tune

# Offline validation of the generated retraining artifacts (no training).
retraining-check:
	$(RETRAIN_ENV) $(UV) run --group ml --group retraining python -m mlops.retraining.runner check --mode smoke

# Rollback is DRY-RUN by default and mutates nothing. Use model-rollback-confirm
# (or ROLLBACK_CONFIRM=true) to actually move the champion alias.
model-rollback:
	$(RETRAIN_ENV) $(UV) run --group ml --group retraining python -m mlops.retraining.runner rollback --mode smoke

model-rollback-confirm:
	$(RETRAIN_ENV) ROLLBACK_CONFIRM=true $(UV) run --group ml --group retraining python -m mlops.retraining.runner rollback --mode smoke --confirm

# PR-06 AI Operations Dashboard (read-only artifact visualization).
dashboard:
	$(UV) run --group dashboard streamlit run dashboard/app.py --server.headless true

dashboard-smoke:
	$(UV) run --group dashboard python -m dashboard.smoke

# PR-07 observability: launch the AI Operations API exposing /health and
# /metrics. Local URL: http://localhost:$(INVFORGE_API_PORT)
# (e.g. http://localhost:8001/health and http://localhost:8001/metrics).
observability-api:
	INVFORGE_API_PORT=$(INVFORGE_API_PORT) $(UV) run --group observability uvicorn api.main:app --host 0.0.0.0 --port $(INVFORGE_API_PORT)

# Start/stop the independent local Prometheus + Grafana stack (Docker only).
# Grafana: http://localhost:3000 (local-only dev creds admin/admin).
# Prometheus: http://localhost:9090. Does NOT touch InvenTree compose.
observability-up:
	docker compose -f $(OBSERVABILITY_COMPOSE) up -d

observability-down:
	docker compose -f $(OBSERVABILITY_COMPOSE) down

# Offline smoke test: no Docker, no server, no browser. Runs in < 10s.
observability-smoke:
	$(UV) run --group observability python -m observability.smoke

# PR-08 defensive security: audit log, risk scoring, anomaly detection.
security-audit: generate-data
	$(UV) run --group security --group ml python -m security.pipeline --output artifacts/security/

security-smoke:
	$(UV) run --group security --group ml python security/smoke_check.py --artifacts-dir artifacts/security/

security-check:
	$(UV) run python security/checks.py

trivy-scan:
	@command -v trivy >/dev/null 2>&1 || { echo "trivy not installed; see security/README.md"; exit 1; }
	trivy fs . --exit-code 1 --severity CRITICAL --quiet
	trivy fs . --exit-code 0 --severity HIGH --quiet

sbom:
	@command -v syft >/dev/null 2>&1 || { echo "syft not installed; see security/README.md"; exit 1; }
	@mkdir -p artifacts/security
	syft . -o cyclonedx-json > artifacts/security/sbom.cyclonedx.json

# PR-10 deployment: validate deploy profiles/templates (offline, no cloud).
deploy-validate:
	$(UV) run --group ml python scripts/validate_deploy_profiles.py

# Read-only deploy smoke check against a running API (local or cloud URL).
# Usage: make deploy-smoke BASE_URL=https://your-service.example.run.app
deploy-smoke:
	$(UV) run python scripts/deploy_smoke.py --base-url $(BASE_URL)

# Build the deployable AI Operations Layer image (runtime-only; see Dockerfile).
docker-build-ai:
	docker build -t $(AI_IMAGE) .

# Build, run (demo/read-only), smoke, and tear down the AI Operations container.
docker-smoke: docker-build-ai
	@docker rm -f invforge-ai-smoke >/dev/null 2>&1 || true
	docker run -d --name invforge-ai-smoke -e INVFORGE_ENV=demo \
		-e PORT=$(INVFORGE_API_PORT) -p $(INVFORGE_API_PORT):$(INVFORGE_API_PORT) $(AI_IMAGE)
	@echo "Waiting for /health..."; \
	for i in $$(seq 1 30); do \
		curl -fsS $(BASE_URL)/health >/dev/null 2>&1 && break; sleep 1; done
	$(UV) run python scripts/deploy_smoke.py --base-url $(BASE_URL); \
	rc=$$?; docker rm -f invforge-ai-smoke >/dev/null 2>&1 || true; exit $$rc

lint:
	$(UV) run ruff check .

test:
	$(UV) run pytest

secrets-scan:
	$(UV) run detect-secrets scan --baseline .secrets.baseline

ci: lint test generate-data validate-data docker-config
	@echo "CI checks passed."
