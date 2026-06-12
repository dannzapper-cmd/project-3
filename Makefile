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
# PR-11A local Kubernetes (AI layer only). Image names MUST match Helm values
# (deploy/k8s/helm/invforge/values.yaml): aiApi.image=invforge-ai-ops:local,
# retraining.image=invforge-retraining:local, bentoml.image=<service>:<tag>.
KIND_CLUSTER ?= invforge-local
KIND_CONFIG := deploy/k8s/kind-config.yaml
HELM_RELEASE ?= invforge
HELM_CHART := deploy/k8s/helm/invforge
K8S_NAMESPACE ?= invforge-ai
RETRAIN_IMAGE ?= invforge-retraining:local
DASHBOARD_IMAGE ?= invforge-dashboard:local
DASHBOARD_PORT ?= 8501
LIVE_API_URL ?= https://invforge-ai-demo-lwcelvo7ya-uc.a.run.app
LIVE_DASHBOARD_URL ?= https://invforge-dashboard-demo-lwcelvo7ya-uc.a.run.app
BENTO_IMAGE ?= invforge_demand_forecast:local
# PR-11B optional observability + lineage profiles (NEVER started by k8s-up).
OBS_CHART := deploy/k8s/observability
OBS_RELEASE ?= invforge-obs
OBS_NAMESPACE ?= invforge-observability
LINEAGE_CHART := deploy/k8s/lineage
LINEAGE_RELEASE ?= invforge-lineage
LINEAGE_NAMESPACE ?= invforge-lineage

.PHONY: help docker-config docker-up docker-down docker-logs docker-init api-dev api-health ingest-inventree generate-data validate-data dvc-repro train-ml decision-intel mlops-loop demo-local reviewer-demo dashboard dashboard-smoke docker-build-dashboard dashboard-docker-smoke observability-api observability-up observability-down observability-smoke security-audit security-smoke security-check trivy-scan sbom deploy-validate deploy-smoke docker-build-ai docker-smoke lint test secrets-scan ci k8s-preflight k8s-up k8s-down k8s-load-images k8s-deploy k8s-status k8s-smoke k8s-logs helm-lint helm-template bento-build bento-containerize k8s-load-bento k8s-retrain-image k8s-retrain model-switch-blue model-switch-green model-switch-rollback obs-k8s-up obs-k8s-down obs-k8s-status obs-k8s-smoke obs-k8s-logs obs-k8s-port-forward obs-k8s-alert-test obs-k8s-lint obs-k8s-template lineage-up lineage-down lineage-status lineage-smoke lineage-port-forward lineage-lint

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
	@echo "  demo-local      Run full local synthetic pipeline (generate → train → intel → mlops)"
	@echo "  reviewer-demo   demo-local + printed next steps for reviewers"
	@echo "  dashboard       Launch PR-06 Streamlit AI Operations dashboard"
	@echo "  dashboard-smoke Non-interactive dashboard loader smoke check"
	@echo "  docker-build-dashboard  Build Cloud Run dashboard image"
	@echo "  dashboard-docker-smoke  Build+run dashboard container with auth smoke"
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
	@echo "  --- PR-11A Kubernetes (AI layer only; local kind) ---"
	@echo "  k8s-preflight   Check kind/kubectl/helm + warn if InvenTree is up"
	@echo "  k8s-up          Create local kind cluster and load the AI image"
	@echo "  k8s-load-images kind load the AI Ops image into the cluster"
	@echo "  k8s-deploy      helm upgrade --install the AI layer chart"
	@echo "  k8s-status      Show nodes/namespaces/pods/services"
	@echo "  k8s-smoke       Port-forward the AI API and curl /health + /metrics"
	@echo "  k8s-logs        Tail AI API pod logs"
	@echo "  k8s-down        Delete the local kind cluster"
	@echo "  helm-lint       helm lint the chart"
	@echo "  helm-template   helm template the chart (default values)"
	@echo "  bento-build         Build a Bento bundle (prereq: champion model)"
	@echo "  bento-containerize  Containerize the Bento into a Docker image"
	@echo "  k8s-load-bento      kind load the BentoML image"
	@echo "  k8s-retrain-image   Build the isolated retraining image"
	@echo "  k8s-retrain         Build+load retraining image and create the Job"
	@echo "  model-switch-blue   Blue-green: point BentoML Service at blue"
	@echo "  model-switch-green  Blue-green: point BentoML Service at green"
	@echo "  model-switch-rollback Blue-green: revert active color to blue"
	@echo "  --- PR-11B Advanced Observability (optional; local kind) ---"
	@echo "  obs-k8s-up          Install observability stack (Prometheus/Grafana/Loki/Tempo/AlertManager)"
	@echo "  obs-k8s-down        Uninstall observability stack"
	@echo "  obs-k8s-status      Show observability pods/services"
	@echo "  obs-k8s-port-forward Port-forward Grafana/Prometheus/Loki/Tempo/AlertManager"
	@echo "  obs-k8s-smoke       Health-check the stack + verify a real metric"
	@echo "  obs-k8s-alert-test  End-to-end alert loop (AI down -> webhook log)"
	@echo "  obs-k8s-logs        Tail the alert webhook receiver logs"
	@echo "  --- PR-11B Data Lineage (optional; local kind) ---"
	@echo "  lineage-up          Install Marquez (OpenLineage server) + ephemeral DB"
	@echo "  lineage-down        Uninstall Marquez"
	@echo "  lineage-status      Show lineage pods/services"
	@echo "  lineage-port-forward Port-forward Marquez UI + API"
	@echo "  lineage-smoke       Emit a real OpenLineage event and verify in Marquez"

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

# Full local synthetic demo chain (deterministic seed 42). Does not start
# InvenTree, the API, or Streamlit — only generates local artifacts.
demo-local: generate-data validate-data train-ml decision-intel mlops-loop dashboard-smoke
	@echo ""
	@echo "Local synthetic pipeline complete."
	@echo "  Artifacts: artifacts/decision/ artifacts/mlops/"
	@echo "  Next: make dashboard  (http://localhost:8501)"
	@echo "  Optional API: make observability-api  (http://localhost:$(INVFORGE_API_PORT)/health)"

# Reviewer-friendly wrapper: one command, clear follow-on steps.
reviewer-demo: demo-local
	@echo ""
	@echo "=== InvForge reviewer demo — next steps ==="
	@echo "1. Launch dashboard:  make dashboard"
	@echo "   Open:             http://localhost:8501"
	@echo "2. Optional API:      make observability-api"
	@echo "   Health:           http://localhost:$(INVFORGE_API_PORT)/health"
	@echo "   Metrics:          http://localhost:$(INVFORGE_API_PORT)/metrics"
	@echo "   OpenAPI docs:     http://localhost:$(INVFORGE_API_PORT)/docs"
	@echo "3. Live cloud API:    $(LIVE_API_URL)/docs"
	@echo "4. Live dashboard:    $(LIVE_DASHBOARD_URL)"
	@echo "5. Reviewer guide:    docs/REVIEWER_DEMO_GUIDE.md"
	@echo "6. Sample inputs:     examples/demo-scenario/scenario.yaml"
	@echo "                      examples/api/forecast_request.json"
	@echo "7. Test cloud auth locally (optional):"
	@echo "   INVFORGE_DEMO_AUTH_ENABLED=true INVFORGE_DEMO_USER=reviewer INVFORGE_DEMO_PASSWORD=invforge-demo make dashboard"
	@echo ""
	@echo "Artifacts generated under: artifacts/decision/ artifacts/mlops/ data/synthetic/output/"

# PR-06 AI Operations Dashboard (read-only artifact visualization).
dashboard:
	PYTHONPATH=. $(UV) run --group dashboard streamlit run dashboard/app.py --server.headless true

dashboard-smoke:
	$(UV) run --group dashboard python -m dashboard.smoke

docker-build-dashboard:
	docker build -f Dockerfile.dashboard -t $(DASHBOARD_IMAGE) .

# Build, run cloud-mode dashboard container, verify auth gate + health, tear down.
dashboard-docker-smoke: docker-build-dashboard
	@docker rm -f invforge-dashboard-smoke >/dev/null 2>&1 || true
	docker run -d --name invforge-dashboard-smoke \
		-e INVFORGE_ENV=cloud \
		-e INVFORGE_DEMO_AUTH_ENABLED=true \
		-e INVFORGE_DEMO_USER=reviewer \
		-e INVFORGE_DEMO_PASSWORD=invforge-demo-smoke \
		-e INVFORGE_API_BASE_URL=$(LIVE_API_URL) \
		-e PORT=$(DASHBOARD_PORT) \
		-p $(DASHBOARD_PORT):$(DASHBOARD_PORT) \
		$(DASHBOARD_IMAGE)
	@echo "Waiting for Streamlit health..."; \
	for i in $$(seq 1 45); do \
		curl -fsS http://localhost:$(DASHBOARD_PORT)/_stcore/health >/dev/null 2>&1 && break; sleep 1; done
	@echo "Checking unauthenticated response contains login gate..."
	@curl -fsS http://localhost:$(DASHBOARD_PORT)/ | grep -qi "Reviewer Demo" || \
		{ echo "ERROR: login gate not visible"; docker logs invforge-dashboard-smoke; docker rm -f invforge-dashboard-smoke; exit 1; }
	@echo "Dashboard docker smoke passed."
	@docker rm -f invforge-dashboard-smoke >/dev/null 2>&1 || true

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
	@# Skip local venv/ML caches (not in CI checkout). Scan repo sources + uv.lock.
	trivy fs . --skip-dirs .venv --skip-dirs mlruns --skip-dirs .git \
		--skip-dirs .pytest_cache --skip-dirs .ruff_cache --skip-dirs artifacts \
		--exit-code 1 --severity CRITICAL --quiet
	trivy fs . --skip-dirs .venv --skip-dirs mlruns --skip-dirs .git \
		--skip-dirs .pytest_cache --skip-dirs .ruff_cache --skip-dirs artifacts \
		--exit-code 0 --severity HIGH --quiet

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

# ---------------------------------------------------------------------------
# PR-11A — local Kubernetes for the AI layer ONLY (kind + Helm).
# InvenTree stays in Docker Compose and is NEVER deployed to Kubernetes.
# No cloud resources are created. See docs/runbooks/k8s-startup.md.
# ---------------------------------------------------------------------------

# Static chart validation (no cluster required).
helm-lint:
	helm lint $(HELM_CHART) -f $(HELM_CHART)/values.yaml

helm-template:
	helm template $(HELM_RELEASE) $(HELM_CHART) \
		-f $(HELM_CHART)/values.yaml -f $(HELM_CHART)/values-local.yaml \
		-n $(K8S_NAMESPACE)

# Verify tooling and warn if InvenTree Compose is running (8 GB RAM safety).
k8s-preflight:
	@bash deploy/k8s/scripts/preflight.sh

# Create the local cluster and load the AI Ops image. Build the image first:
#   make docker-build-ai
# Hard stop if InvenTree Compose is up to avoid OOM on an 8 GB laptop.
k8s-up: k8s-preflight
	@echo "WARNING: If InvenTree Docker Compose is running, stop it first with 'make docker-down' to avoid OOM on 8 GB RAM."
	@docker compose -f $(COMPOSE_FILE) ps --quiet 2>/dev/null | grep -q . \
		&& { echo "ERROR: Stop InvenTree stack first (make docker-down)"; exit 1; } || true
	@kind get clusters 2>/dev/null | grep -qx $(KIND_CLUSTER) \
		&& echo "kind cluster '$(KIND_CLUSTER)' already exists." \
		|| kind create cluster --config $(KIND_CONFIG)
	$(MAKE) k8s-load-images

# kind runs an isolated runtime: host-built images MUST be loaded explicitly,
# otherwise pods stay in ErrImagePull. Run AFTER `make docker-build-ai`.
k8s-load-images:
	@docker image inspect $(AI_IMAGE) >/dev/null 2>&1 \
		|| { echo "ERROR: image $(AI_IMAGE) not found. Run 'make docker-build-ai' first."; exit 1; }
	kind load docker-image $(AI_IMAGE) --name $(KIND_CLUSTER)

# Install/upgrade the AI layer chart (AI Ops API only by default).
k8s-deploy:
	helm upgrade --install $(HELM_RELEASE) $(HELM_CHART) \
		-n $(K8S_NAMESPACE) --create-namespace \
		-f $(HELM_CHART)/values.yaml -f $(HELM_CHART)/values-local.yaml \
		--set aiApi.image.repository=$(word 1,$(subst :, ,$(AI_IMAGE))) \
		--set aiApi.image.tag=$(word 2,$(subst :, ,$(AI_IMAGE)))

k8s-status:
	kubectl get nodes
	kubectl get ns | grep -E 'invforge|NAME' || true
	kubectl get pods,svc -n $(K8S_NAMESPACE)

k8s-smoke:
	@bash deploy/k8s/scripts/smoke.sh $(K8S_NAMESPACE) $(HELM_RELEASE)

k8s-logs:
	kubectl logs -n $(K8S_NAMESPACE) -l app.kubernetes.io/component=ai-api --tail=100 -f

k8s-down:
	kind delete cluster --name $(KIND_CLUSTER)

# --- BentoML model server (deferred image build; one-command after PR-11A) ---
# Prereq: a champion model packaged in the local BentoML store (make mlops-loop).
bento-build:
	BENTOML_DO_NOT_TRACK=true $(UV) run --group ml --group mlops \
		bentoml build -f deploy/k8s/bentofile.yaml .

# Containerize the latest Bento into a Docker image tagged $(BENTO_IMAGE).
bento-containerize:
	BENTOML_DO_NOT_TRACK=true $(UV) run --group ml --group mlops \
		bentoml containerize invforge_demand_forecast:latest -t $(BENTO_IMAGE)

k8s-load-bento:
	@docker image inspect $(BENTO_IMAGE) >/dev/null 2>&1 \
		|| { echo "ERROR: image $(BENTO_IMAGE) not found. Run 'make bento-build && make bento-containerize' first."; exit 1; }
	kind load docker-image $(BENTO_IMAGE) --name $(KIND_CLUSTER)

# --- Retraining image + Job (isolated image with ml+retraining groups) -------
k8s-retrain-image:
	docker build -f deploy/k8s/Dockerfile.retraining -t $(RETRAIN_IMAGE) .

# Build the retraining image, load it into kind, and run a one-shot Job.
k8s-retrain: k8s-retrain-image
	kind load docker-image $(RETRAIN_IMAGE) --name $(KIND_CLUSTER)
	helm upgrade --install $(HELM_RELEASE) $(HELM_CHART) \
		-n $(K8S_NAMESPACE) --create-namespace \
		-f $(HELM_CHART)/values.yaml -f $(HELM_CHART)/values-local.yaml \
		--set retraining.job.enabled=true \
		--set retraining.image.repository=$(word 1,$(subst :, ,$(RETRAIN_IMAGE))) \
		--set retraining.image.tag=$(word 2,$(subst :, ,$(RETRAIN_IMAGE)))
	@echo "Retraining Job created. Follow it with:"
	@echo "  kubectl get jobs,pods -n $(K8S_NAMESPACE) -l app.kubernetes.io/component=retraining"

# --- Blue-green model switch (requires a deployed BentoML image) --------------
model-switch-blue:
	@bash deploy/k8s/scripts/model-switch.sh blue $(K8S_NAMESPACE) $(HELM_RELEASE)

model-switch-green:
	@bash deploy/k8s/scripts/model-switch.sh green $(K8S_NAMESPACE) $(HELM_RELEASE)

# Rollback the blue-green Service selector to the stable (blue) color.
model-switch-rollback:
	@bash deploy/k8s/scripts/model-switch.sh blue $(K8S_NAMESPACE) $(HELM_RELEASE)

# ---------------------------------------------------------------------------
# PR-11B — advanced observability (OPTIONAL profile; never part of k8s-up).
# Separate namespace invforge-observability. InvenTree is never deployed here.
# RAM: stop InvenTree Compose (make docker-down) before running. See
# docs/runbooks/observability-startup.md.
# ---------------------------------------------------------------------------
obs-k8s-lint:
	helm lint $(OBS_CHART)

obs-k8s-template:
	helm template $(OBS_RELEASE) $(OBS_CHART) -n $(OBS_NAMESPACE)

obs-k8s-up:
	@echo "NOTE: optional observability profile. Ensure InvenTree Compose is stopped (make docker-down)."
	helm upgrade --install $(OBS_RELEASE) $(OBS_CHART) \
		-n $(OBS_NAMESPACE) --create-namespace

obs-k8s-down:
	-helm uninstall $(OBS_RELEASE) -n $(OBS_NAMESPACE)
	-kubectl delete namespace $(OBS_NAMESPACE) --ignore-not-found

obs-k8s-status:
	kubectl get pods,svc -n $(OBS_NAMESPACE)

obs-k8s-port-forward:
	@bash $(OBS_CHART)/scripts/port-forward.sh $(OBS_NAMESPACE)

obs-k8s-smoke:
	@bash $(OBS_CHART)/scripts/smoke.sh

obs-k8s-alert-test:
	@bash $(OBS_CHART)/scripts/alert-test.sh

obs-k8s-logs:
	kubectl logs -n $(OBS_NAMESPACE) -l app.kubernetes.io/component=alert-webhook-receiver --tail=100 -f

# ---------------------------------------------------------------------------
# PR-11B — data lineage with Marquez/OpenLineage (OPTIONAL; never part of k8s-up).
# Separate namespace invforge-lineage. See docs/runbooks/lineage-inspection.md.
# ---------------------------------------------------------------------------
lineage-lint:
	helm lint $(LINEAGE_CHART)

lineage-up:
	helm upgrade --install $(LINEAGE_RELEASE) $(LINEAGE_CHART) \
		-n $(LINEAGE_NAMESPACE) --create-namespace

lineage-down:
	-helm uninstall $(LINEAGE_RELEASE) -n $(LINEAGE_NAMESPACE)
	-kubectl delete namespace $(LINEAGE_NAMESPACE) --ignore-not-found

lineage-status:
	kubectl get pods,svc -n $(LINEAGE_NAMESPACE)

lineage-port-forward:
	@bash $(LINEAGE_CHART)/scripts/port-forward.sh $(LINEAGE_NAMESPACE)

# Emits ONE real OpenLineage event via the verified retraining pipeline and
# confirms Marquez recorded it. Requires `make lineage-port-forward` first.
lineage-smoke:
	@bash $(LINEAGE_CHART)/scripts/smoke.sh
