# InvForge Makefile
# Common development and CI commands for PR-01 base setup.

UV ?= uv
COMPOSE_FILE := app/docker-compose.yml
COMPOSE_ENV := app/.env
COMPOSE := docker compose -f $(COMPOSE_FILE) --env-file $(COMPOSE_ENV)
OUTPUT_DIR := data/synthetic/output
SEED := 42

.PHONY: help docker-config docker-up docker-down docker-logs docker-init generate-data lint secrets-scan ci

help:
	@echo "InvForge — available targets:"
	@echo "  docker-config   Validate Docker Compose configuration"
	@echo "  docker-up       Start InvenTree base stack"
	@echo "  docker-down     Stop InvenTree base stack"
	@echo "  docker-logs     Tail InvenTree stack logs"
	@echo "  docker-init     Run first-time InvenTree DB/static setup (invoke update)"
	@echo "  generate-data   Generate deterministic synthetic inventory CSVs"
	@echo "  lint            Run Ruff linter"
	@echo "  secrets-scan    Scan repository for secrets"
	@echo "  ci              Run local CI checks (lint + generator + compose config)"

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

generate-data:
	$(UV) run python data/synthetic/generate_inventory_data.py --output $(OUTPUT_DIR) --seed $(SEED)

lint:
	$(UV) run ruff check .

secrets-scan:
	$(UV) run detect-secrets scan --baseline .secrets.baseline

ci: lint generate-data docker-config
	@echo "CI checks passed."
