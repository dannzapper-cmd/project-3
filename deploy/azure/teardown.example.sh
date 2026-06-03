#!/usr/bin/env bash
# InvForge AI Operations Layer — Azure Container Apps teardown (PR-10 TEMPLATE).
#
# Deletes the Container App, its managed environment, and (optionally) the
# whole resource group. Set the variables below before running. NOT run by CI.
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:?Set RESOURCE_GROUP}"
APP_NAME="${APP_NAME:?Set APP_NAME}"
ENVIRONMENT_NAME="${ENVIRONMENT_NAME:-invforge-env}"

echo ">> Deleting Container App: ${APP_NAME}"
az containerapp delete --name "${APP_NAME}" \
  --resource-group "${RESOURCE_GROUP}" --yes || true

echo ">> Deleting Container Apps environment: ${ENVIRONMENT_NAME}"
az containerapp env delete --name "${ENVIRONMENT_NAME}" \
  --resource-group "${RESOURCE_GROUP}" --yes || true

cat <<'EOF'
>> Also remove (to fully stop charges) — review and delete manually:
   - Azure Container Registry (ACR): az acr delete --name <registry>
   - Any Front Door / Application Gateway WAF policy + endpoint
   - Log Analytics workspace backing the environment
   - Key Vault secrets you created
>> To delete EVERYTHING in the resource group (DESTRUCTIVE), uncomment:
#  az group delete --name "${RESOURCE_GROUP}" --yes
EOF
