# Azure Container Apps — activation guide

> **PR-13 status:** Documentation only. **Not executed in PR-13.** No Azure
> resources were created. This is a **reproducibility profile/template**, not a
> live deployment.

## What gets deployed

Only the **AI Operations API** container on **Azure Container Apps**
(scale-to-zero serverless containers).

Read-only surface per [deployment contract](../deployment-contract.md).

## Prerequisites

- Azure subscription
- `az` CLI logged in (`az login`)
- `containerapp` extension: `az extension add --name containerapp`
- Azure Container Registry (ACR) or other registry

## Environment variables

```bash
cp deploy/azure/env.example deploy/azure/.env
# Edit: RESOURCE_GROUP, LOCATION, REGISTRY_SERVER, APP_NAME
```

Container env (in template):

| Var | Value |
|-----|-------|
| `INVFORGE_ENV` | `cloud` |
| `INVFORGE_DEMO_MODE` | `true` |
| `INVFORGE_ALLOW_MUTATIONS` | `false` |
| `LOG_LEVEL` | `INFO` |
| `PORT` | `8001` |

## Build and push

```bash
export REGISTRY_SERVER=myregistry.azurecr.io
export IMAGE_URI="${REGISTRY_SERVER}/invforge/ai-ops:latest"

az acr login --name "${REGISTRY_SERVER%%.*}"
docker build -t "${IMAGE_URI}" .
docker push "${IMAGE_URI}"
```

## Deploy

```bash
export RESOURCE_GROUP=invforge-rg LOCATION=eastus
export ENVIRONMENT_NAME=invforge-env APP_NAME=invforge-ai-ops

az group create --name "${RESOURCE_GROUP}" --location "${LOCATION}"
az containerapp env create --name "${ENVIRONMENT_NAME}" \
  --resource-group "${RESOURCE_GROUP}" --location "${LOCATION}"

# Replace placeholders in deploy/azure/container-app.template.yaml first
az containerapp create --name "${APP_NAME}" \
  --resource-group "${RESOURCE_GROUP}" \
  --environment "${ENVIRONMENT_NAME}" \
  --yaml deploy/azure/container-app.template.yaml
```

## Smoke test

```bash
URL=$(az containerapp show --name "${APP_NAME}" --resource-group "${RESOURCE_GROUP}" \
  --query 'properties.configuration.ingress.fqdn' -o tsv)
python scripts/deploy_smoke.py --base-url "https://${URL}"
```

## Teardown

```bash
export RESOURCE_GROUP=... APP_NAME=... ENVIRONMENT_NAME=...
./deploy/azure/teardown.example.sh
```

Also delete ACR, Front Door/WAF, Log Analytics workspace if created.

## Cost warning

- `minReplicas: 0` → scale to zero when idle; cold starts apply
- `maxReplicas: 3` caps burst cost
- Container Apps, ACR, egress, and Log Analytics workspace incur charges
- New accounts may include monthly Container Apps grant — **verify current Azure pricing**

## Secret handling

- Use Container Apps secrets or Key Vault references for tokens
- Prefer Key Vault for production-like setups

## WAF (optional)

`deploy/azure/waf-policy.template.json` — attach via Azure Front Door or
Application Gateway WAF v2 (not included in Container Apps ingress alone).

## Source of truth

[deploy/azure/README.md](../../deploy/azure/README.md)

## Not executed in PR-13

No `az` commands were run. Full Bicep/Terraform IaC deferred to production hardening.
