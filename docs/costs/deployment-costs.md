# Deployment Costs & Teardown (PR-10)

Honest, hedged cost guidance for deploying the InvForge AI Operations Layer.
**No cost is guaranteed.** All provider figures are **examples**, not promises —
verify current pricing/free-tier limits in the official provider docs before
deploying.

> InvForge does **not** maintain active GCP/AWS/Azure deployments by default.
> The cloud profiles are activation-ready templates; nothing is billed unless
> **you** deploy with your own account.

## Local mode

Running everything locally (API, MLOps loop, dashboard, InvenTree stack) costs
**$0** in cloud charges — it uses your own machine/Docker only.

## Primary cloud demo mode

A low-traffic, read-only demo of the AI Operations API can often stay near
free-tier levels, **depending on account eligibility, region, request volume,
image storage, logs, and current provider pricing.** Actual costs may change;
verify official pricing before enabling public access.

### What can cause charges

- **Compute time** while serving requests (and always-on instances if you
  disable scale-to-zero).
- **Container image storage** in the provider registry.
- **Logs** ingestion/retention.
- **Egress** (data transfer out).
- **Load balancer + WAF** (if you front the service for WAF/DDoS).
- Leaving resources running after the demo.

### Provider notes (examples — verify before deploying)

- **GCP Cloud Run:** charges for request/CPU/memory time; scale-to-zero
  (`minScale: 0`) avoids idle compute cost (cold-start trade-off). Artifact
  Registry storage and logs add cost. Cloud Armor/load balancer (if used) bill
  separately. Free-tier request/compute grants may apply — *verify current
  limits in the GCP docs.*
- **AWS ECS/Fargate:** bills per vCPU-second and GB-second **while tasks run**
  (no scale-to-zero like Cloud Run — set `desiredCount: 0` to pause). ECR image
  storage, CloudWatch Logs ingestion, ALB hours, and WAF requests add cost.
  *Verify current Fargate/ECR/CloudWatch pricing in the AWS docs.*
- **Azure Container Apps:** bills per vCPU-second and GiB-second of active usage;
  `minReplicas: 0` enables scale-to-zero. ACR storage, the backing Log Analytics
  workspace, egress, and Front Door/WAF (if used) add cost. New accounts may
  include a monthly free grant, but *this changes — verify current limits in the
  Azure docs.*

## How to shut down resources (teardown)

Always tear down after a demo. Provider-specific steps live in the profile
READMEs and scripts:

- **GCP:** `deploy/gcp/teardown.example.sh` (delete Cloud Run service; optionally
  the Artifact Registry image). Also review Secret Manager and any load
  balancer / Cloud Armor.
- **AWS:** `deploy/aws/teardown.example.sh` (scale to 0, delete service,
  deregister task defs). Also delete the ALB/target group, ECR repo, CloudWatch
  log group, WAF Web ACL, and secrets.
- **Azure:** `deploy/azure/teardown.example.sh` (delete the Container App and
  environment). Also delete ACR, Front Door/WAF, Log Analytics, and Key Vault
  secrets.

```bash
# Examples (set the required vars first; see each README):
PROJECT_ID=... REGION=... SERVICE_NAME=... ./deploy/gcp/teardown.example.sh
REGION=... CLUSTER=... SERVICE_NAME=... ./deploy/aws/teardown.example.sh
RESOURCE_GROUP=... APP_NAME=... ./deploy/azure/teardown.example.sh
```

## PR-10 vs PR-11 cost posture

- PR-10 maintains **no active** GCP/AWS/Azure deployments by default — costs are
  $0 unless you deploy.
- PR-11's local Kubernetes (kind/k3s) path can be run **without active cloud
  clusters**, so it also incurs **$0** cloud cost when run locally.
