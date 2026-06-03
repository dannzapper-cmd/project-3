# InvForge AI Operations Layer — deployable runtime image (PR-10).
#
# Scope: this image packages ONLY the external AI Operations API (the FastAPI
# sidecar in api/ plus the read-only observability/ health+metrics layer). It is
# the single deployable surface for the GCP Cloud Run / AWS ECS-Fargate / Azure
# Container Apps profiles under deploy/.
#
# It intentionally does NOT include:
#   - InvenTree core (the sidecar pattern keeps InvenTree external/unchanged)
#   - ML / MLOps / retraining dependency groups (lightgbm, mlflow, zenml, optuna)
#   - the Streamlit dashboard
#   - local mlruns/, artifacts/, data/, notebooks/ (see .dockerignore)
#
# Runtime deps = the project's core dependencies + the lightweight
# `observability` group (prometheus-client) so /metrics works. No dev/ml groups.

# ---- Builder: resolve runtime venv with uv -------------------------------
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Only the dependency manifest is needed to build the venv (package = false).
COPY pyproject.toml ./

# Core deps + observability group only. Exclude dev and all heavy ML/MLOps/
# retraining/dashboard groups so the runtime image stays small.
RUN uv sync --no-dev --no-install-project --group observability

# ---- Runtime: minimal slim image -----------------------------------------
FROM python:3.12-slim-bookworm AS runtime

# Cloud-safe defaults: read-only demo surface, mutations blocked, health stays
# 200 for provider probes even without local artifacts. Override per provider.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    INVFORGE_ENV=cloud \
    PORT=8001

WORKDIR /app

# Non-root runtime user.
RUN useradd --create-home --uid 10001 appuser

# Virtualenv from the builder, then only the deployable source packages.
COPY --from=builder /app/.venv /app/.venv
COPY api ./api
COPY observability ./observability

USER appuser

EXPOSE 8001

# Liveness against the confirmed /health endpoint (no extra tooling: pure
# stdlib urllib so the slim image needs no curl). Honors the injected PORT.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,sys,urllib.request; \
url='http://127.0.0.1:'+os.environ.get('PORT','8001')+'/health'; \
sys.exit(0 if urllib.request.urlopen(url, timeout=3).status==200 else 1)"

# Bind to the provider-injected PORT (Cloud Run/Container Apps/Fargate set it).
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8001}"]
