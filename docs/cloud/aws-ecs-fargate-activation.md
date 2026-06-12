# AWS ECS Fargate — activation guide

> **PR-13 status:** Documentation only. **Not executed in PR-13.** No AWS
> resources were created. This is a **reproducibility profile/template**, not a
> live deployment.

## What gets deployed

Only the **AI Operations API** container on **ECS Fargate** behind an ALB.

Read-only surface: `/health`, `/metrics`, `/v1/inventory/status`, `/v1/data/summary`.
Mutation endpoint blocked in cloud mode.

## Why ECS Fargate (not App Runner)

AWS App Runner is no longer open to new customers. ECS Fargate is the documented
container target. See [deploy/aws/README.md](../../deploy/aws/README.md).

## Prerequisites

- AWS account with appropriate IAM permissions
- AWS CLI configured (`aws configure`)
- VPC, subnets, ALB, ECS cluster (you create these — template does not provision IaC)
- ECR repository for the image
- Docker for build/push

## Environment variables

```bash
cp deploy/aws/env.example deploy/aws/.env
# Edit: ACCOUNT_ID, REGION, CLUSTER, SERVICE_NAME, etc.
```

Container env (in task definition template):

| Var | Value |
|-----|-------|
| `INVFORGE_ENV` | `cloud` |
| `INVFORGE_DEMO_MODE` | `true` |
| `INVFORGE_ALLOW_MUTATIONS` | `false` |
| `LOG_LEVEL` | `INFO` |
| `PORT` | `8001` |

## Build and push to ECR

```bash
export ACCOUNT_ID=000000000000 REGION=us-east-1
export IMAGE_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/invforge/ai-ops:latest"

aws ecr create-repository --repository-name invforge/ai-ops --region "${REGION}"
aws ecr get-login-password --region "${REGION}" | docker login --username AWS \
  --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

docker build -t "${IMAGE_URI}" .
docker push "${IMAGE_URI}"
```

## Register task definition and create service

1. Replace placeholders in `deploy/aws/ecs-fargate-task-definition.template.json`
2. Register:

```bash
aws ecs register-task-definition \
  --cli-input-json file://deploy/aws/ecs-fargate-task-definition.template.json \
  --region "${REGION}"
```

3. Create ECS service on Fargate attached to ALB target group (port 8001)

## Smoke test

```bash
python scripts/deploy_smoke.py --base-url "https://your-alb-dns-name"
```

## Teardown

```bash
export REGION=... CLUSTER=... SERVICE_NAME=...
./deploy/aws/teardown.example.sh
```

Remove ALB, ECR repo, CloudWatch log group, WAF Web ACL separately.

## Cost warning

- Fargate bills per vCPU-second and GB-second **while tasks run** (no scale-to-zero)
- Set `desiredCount: 0` to pause; ECR, ALB, CloudWatch, and WAF add cost
- **Verify current AWS pricing before deploying**

## Secret handling

- Use AWS Secrets Manager for `INVENTREE_API_TOKEN` (optional)
- Task execution role needs secret read; task role stays minimal

## WAF (optional)

`deploy/aws/waf-web-acl.template.json` — associate with ALB manually.

## Source of truth

[deploy/aws/README.md](../../deploy/aws/README.md)

## Not executed in PR-13

No `aws` commands were run. Full IaC deferred to production hardening.
