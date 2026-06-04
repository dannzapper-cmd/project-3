# Azure — Container Apps deploy profile (PR-10)

> **Status:** Deployment profile available. **Not actively deployed.** Activate
> manually with your own Azure subscription. No live Azure resources are created
> by InvForge or CI.

This profile targets **Azure Container Apps** (serverless containers with
scale-to-zero) for the InvForge AI Operations Layer. **AKS / Kubernetes is
deferred to PR-11 Senior Edition.**

## What gets deployed

Only the **AI Operations API** container (repo-root `Dockerfile`), exposing the
SAFE read-only surface (`/health`, `/metrics`, `/v1/inventory/status`,
`/v1/data/summary`). The mutation endpoint is blocked in cloud mode. See
`docs/deployment-contract.md`.

## Files

| File | Purpose |
|------|---------|
| `container-app.template.yaml` | Container Apps spec (`az containerapp create --yaml`) — placeholders only |
| `env.example` | Deploy variables template |
| `waf-policy.template.json` | Front Door WAF policy template (activation-ready, not live) |
| `teardown.example.sh` | Delete the app + environment |

## Prerequisites

- An Azure subscription.
- `az` CLI logged in (`az login`) with the `containerapp` extension
  (`az extension add --name containerapp`).
- An **Azure Container Registry (ACR)** (or other registry) for the image.

## Container registry / image expectation

```bash
export REGISTRY_SERVER=myregistry.azurecr.io
export IMAGE_URI="${REGISTRY_SERVER}/invforge/ai-ops:latest"
az acr login --name "${REGISTRY_SERVER%%.*}"
docker build -t "${IMAGE_URI}" .
docker push "${IMAGE_URI}"
```

## Deploy / update

Create the managed environment once, then create the app from the template
(replace placeholders first):

```bash
export RESOURCE_GROUP=invforge-rg LOCATION=eastus
export ENVIRONMENT_NAME=invforge-env APP_NAME=invforge-ai-ops

az group create --name "${RESOURCE_GROUP}" --location "${LOCATION}"
az containerapp env create --name "${ENVIRONMENT_NAME}" \
  --resource-group "${RESOURCE_GROUP}" --location "${LOCATION}"

az containerapp create --name "${APP_NAME}" \
  --resource-group "${RESOURCE_GROUP}" \
  --environment "${ENVIRONMENT_NAME}" \
  --yaml deploy/azure/container-app.template.yaml
```

## Env vars and secret references

| Var | Type | Notes |
|-----|------|-------|
| `PORT` | plain | Container listen port (8001) |
| `INVFORGE_ENV` | plain | `cloud` |
| `INVFORGE_DEMO_MODE` | plain | `true` (health stays 200 without local artifacts) |
| `INVFORGE_ALLOW_MUTATIONS` | plain | **`false`** on any public app |
| `LOG_LEVEL` | plain | e.g. `INFO` |
| `INVENTREE_API_TOKEN` | **secret** | Container Apps secret / Key Vault `secretRef`; optional |

The template's `secrets:` block and commented `secretRef` show the pattern.
Prefer Key Vault references for production-like secret storage.

## Health / smoke checks

The template wires Liveness + Startup probes to `/health`. After deploy:

```bash
URL=$(az containerapp show --name "${APP_NAME}" --resource-group "${RESOURCE_GROUP}" \
  --query 'properties.configuration.ingress.fqdn' -o tsv)
python scripts/deploy_smoke.py --base-url "https://${URL}"
```

## WAF / DDoS (Azure Front Door WAF)

`waf-policy.template.json` is an **activation-ready template** (Default + Bot
Manager managed rule sets and a per-IP rate limit). Container Apps ingress alone
does **not** provide WAF — front the app with **Azure Front Door** (or
Application Gateway WAF v2) and attach the policy. WAF is **not active** until
deployed with your own subscription and a Front Door / App Gateway entrypoint.

## Cost notes

- **Scale-to-zero** (`minReplicas: 0`) avoids charges while idle; cold starts are
  the trade-off. `maxReplicas: 3` caps cost.
- Container Apps bills per vCPU-second and GiB-second of active usage; ACR
  charges for image storage; egress and the backing Log Analytics workspace add
  cost; Front Door / WAF (if used) add their own charges.
- New Azure accounts may include a free monthly grant for Container Apps, but
  **this changes** — low-traffic demo can often stay near free-tier levels
  depending on account eligibility, region, request volume, image storage, logs,
  and current provider pricing. **Verify current pricing/free-tier limits in the
  official Azure docs before deploying.** Actual costs may change.

## Teardown

```bash
export RESOURCE_GROUP=... APP_NAME=... ENVIRONMENT_NAME=...
./deploy/azure/teardown.example.sh
```

Also delete the ACR, any Front Door/WAF policy, the Log Analytics workspace, and
Key Vault secrets (the script prints the commands). See
`docs/costs/deployment-costs.md`.

## Limitations

- Not deployed or smoke-tested in CI; no live Azure resources are maintained.
- WAF requires Front Door / Application Gateway (template only).
- Local kind Kubernetes exists under `deploy/k8s`; AKS/cloud Kubernetes remains
  out of scope for this profile.
- Full Bicep/Terraform IaC is **deferred to production hardening**.
