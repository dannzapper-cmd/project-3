# Contributing to InvForge

Thank you for contributing to InvForge — AI Operations Control Tower.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose v2
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Python 3.12+

## Local setup

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dev dependencies
uv sync --group dev

# Copy InvenTree environment template
cp app/.env.example app/.env
```

## Pre-commit hooks (optional)

Pre-commit is **not** installed automatically. To enable local hooks:

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```

Hooks include Ruff, trailing-whitespace, end-of-file-fixer, and detect-secrets.

## Common commands

See the root `Makefile` or run `make help`:

```bash
make generate-data   # Synthetic inventory CSVs
make lint            # Ruff
make secrets-scan    # detect-secrets
make ci              # Lint + tests + data generation/validation + compose config
make docker-up       # Start InvenTree base stack
```

## Architecture principle

InvForge is an **external AI Operations sidecar** on top of InvenTree. Do not modify, fork, or vendor the InvenTree core. Use InvenTree via official Docker images and configuration only.

## PR scope

Follow the 13-PR roadmap in `PROJECT_3_INVFORGE_MASTER_CONTEXT.md`. Keep each PR focused on its defined scope.
