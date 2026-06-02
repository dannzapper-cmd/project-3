# InvForge Makefile
# Common development and CI commands for InvForge.

UV ?= uv
COMPOSE_FILE := app/docker-compose.yml
COMPOSE_ENV := app/.env
COMPOSE := docker compose -f $(COMPOSE_FILE) --env-file $(COMPOSE_ENV)
OUTPUT_DIR := data/synthetic/output
SEED := 42
INVFORGE_API_PORT ?= 8001

.PHONY: help docker-config docker-up docker-down docker-logs docker-init api-dev api-health ingest-inventree generate-data validate-data dvc-repro lint test secrets-scan ci

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

lint:
	$(UV) run ruff check .

test:
	$(UV) run pytest

secrets-scan:
	$(UV) run detect-secrets scan --baseline .secrets.baseline

ci: lint test generate-data validate-data docker-config
	@echo "CI checks passed."
