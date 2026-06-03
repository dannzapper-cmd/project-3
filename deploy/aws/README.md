# AWS — ECS/Fargate deploy profile (PR-10)

> **Status:** This is a **deployment profile and architecture reference**. It has
> **not been actively tested or deployed**. Activate it manually with your own
> AWS account. No live AWS resources are created by InvForge or CI.

This profile targets **Amazon ECS on AWS Fargate** for the InvForge AI
Operations Layer.

> **Why not AWS App Runner?** AWS App Runner is **no longer open to new
> customers**, so it is intentionally **not** the recommended path here.
> ECS/Fargate is the documented container target instead.

## What this profile is (and is not)

- It is a **profile/template**: a valid ECS Fargate task definition, env
  template, WAF template, and teardown script — enough to activate manually.
- It is **not** a Terraform/CDK stack and does **not** provision a VPC, ALB, ECS
  cluster, or IAM roles for you. Those are standard AWS resources you create
  with your own tooling. Full Infrastructure-as-Code is **deferred to production
  hardening** (see the deployment ADR).

## Files

| File | Purpose |
|------|---------|
| `ecs-fargate-task-definition.template.json` | Fargate task definition (placeholders only) |
| `env.example` | Deploy variables template |
| `waf-web-acl.template.json` | AWS WAF Web ACL profile template (activation-ready, not live) |
| `teardown.example.sh` | Delete the service + deregister task defs |

## Concept

```
Internet ──> (optional) WAF Web ACL ──> Application Load Balancer
                                              │
                                              ▼
                                ECS Service (Fargate launch type)
                                              │
                                              ▼
                              Task (invforge-ai-ops container :8001)
```

1. Build the image (repo-root `Dockerfile`) and push to **ECR**.
2. Create the IAM **execution role** (pull image + write logs) and **task role**
   (app runtime perms — minimal/none for the read-only demo).
3. Register the task definition (`ecs-fargate-task-definition.template.json`
   with placeholders replaced).
4. Create/choose an ECS cluster and run an ECS **service** on Fargate, attached
   to an ALB target group on container port `8001`.
5. (Optional) Associate the WAF Web ACL with the ALB.

## ECR image expectation

```bash
export ACCOUNT_ID=000000000000 REGION=us-east-1
export IMAGE_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/invforge/ai-ops:latest"
aws ecr create-repository --repository-name invforge/ai-ops --region "${REGION}"
aws ecr get-login-password --region "${REGION}" | docker login --username AWS \
  --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
docker build -t "${IMAGE_URI}" .
docker push "${IMAGE_URI}"
```

## Register the task definition

Replace `ACCOUNT_ID`, `REGION`, `IMAGE_URI`, `EXECUTION_ROLE_ARN`,
`TASK_ROLE_ARN` in the template, then:

```bash
aws ecs register-task-definition \
  --cli-input-json file://deploy/aws/ecs-fargate-task-definition.template.json \
  --region "${REGION}"
```

The task definition wires:
- `portMappings` → container port `8001`
- `healthCheck` → `/health` (uses the image's bundled Python, no `curl` needed)
- `logConfiguration` → CloudWatch Logs group `/ecs/invforge-ai-ops`
- `secrets` → AWS Secrets Manager (only needed if you enable live ingestion)

## Required env vars / secrets

| Var | Type | Notes |
|-----|------|-------|
| `PORT` | plain | Container listen port (8001) |
| `INVFORGE_ENV` | plain | `cloud` |
| `INVFORGE_DEMO_MODE` | plain | `true` |
| `INVFORGE_ALLOW_MUTATIONS` | plain | **`false`** on any public service |
| `LOG_LEVEL` | plain | e.g. `INFO` |
| `INVENTREE_API_TOKEN` | **secret** | From Secrets Manager ARN; optional (read-only demo needs none) |

## IAM / security notes (high level)

- **Execution role vs task role:** the *execution role* lets ECS pull the image
  and ship logs (`AmazonECSTaskExecutionRolePolicy` + secret read for any
  referenced secret); the *task role* grants the application its own runtime
  permissions (minimal — often none for the read-only demo).
- **Least privilege:** do **not** attach `AdministratorAccess` to the task role.
- Restrict the security group to the ALB and only the needed port.

## WAF / DDoS (AWS WAF)

`waf-web-acl.template.json` is an **activation-ready template** (AWS managed
common + known-bad-inputs rule groups and a per-IP rate limit). WAF is **not
active** until you create the Web ACL and associate it with your ALB:

```bash
aws wafv2 create-web-acl --cli-input-json file://deploy/aws/waf-web-acl.template.json \
  --region "${REGION}"
# then: aws wafv2 associate-web-acl --web-acl-arn <arn> --resource-arn <alb-arn>
```

Activation requires a real AWS account, an ALB public entrypoint, and manual
deployment.

## Cost notes

- **Fargate** bills per vCPU-second and GB-second while tasks run (there is no
  scale-to-zero like Cloud Run; a running service costs even when idle — set
  `desiredCount: 0` to pause).
- **ECR** charges for image storage; **CloudWatch Logs** charges for ingestion
  and retention; **ALB** and **WAF** add hourly + request costs.
- Low-traffic demo costs depend on account eligibility, region, task size,
  runtime hours, image storage, logs, and current provider pricing. **Verify
  current pricing/free-tier limits in the official AWS docs before deploying.**
  Actual costs may change.

## Teardown

```bash
export REGION=... CLUSTER=... SERVICE_NAME=...
./deploy/aws/teardown.example.sh
```

Then remove the ALB/target group, ECR repo, CloudWatch log group, WAF Web ACL,
and any secrets (the script prints the commands). See
`docs/costs/deployment-costs.md`.

## Limitations / why this is a profile, not an active deployment

- Activating requires an AWS account, IAM roles, a VPC/subnets, and an ALB —
  beyond PR-10's no-credentials, no-live-resources scope.
- Not deployed or smoke-tested in CI.
- EKS/Kubernetes on AWS is **deferred to PR-11 Senior Edition**.
- Full Terraform/CDK IaC is **deferred to production hardening**.
