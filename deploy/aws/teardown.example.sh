#!/usr/bin/env bash
# InvForge AI Operations Layer — AWS ECS/Fargate teardown (PR-10 TEMPLATE).
#
# Stops/deletes the ECS service, deregisters the task definition, and points at
# the other resources to clean up. Set the variables below before running.
# This is NOT run by CI.
set -euo pipefail

REGION="${REGION:?Set REGION}"
CLUSTER="${CLUSTER:?Set CLUSTER (ECS cluster name)}"
SERVICE_NAME="${SERVICE_NAME:?Set SERVICE_NAME (ECS service name)}"
TASK_FAMILY="${TASK_FAMILY:-invforge-ai-ops}"

echo ">> Scaling service to 0 and deleting: ${SERVICE_NAME}"
aws ecs update-service --cluster "${CLUSTER}" --service "${SERVICE_NAME}" \
  --desired-count 0 --region "${REGION}" >/dev/null || true
aws ecs delete-service --cluster "${CLUSTER}" --service "${SERVICE_NAME}" \
  --force --region "${REGION}" >/dev/null || true

echo ">> Deregistering task definition revisions for family: ${TASK_FAMILY}"
for arn in $(aws ecs list-task-definitions --family-prefix "${TASK_FAMILY}" \
  --region "${REGION}" --query 'taskDefinitionArns[]' --output text); do
  aws ecs deregister-task-definition --task-definition "${arn}" \
    --region "${REGION}" >/dev/null || true
done

cat <<'EOF'
>> Also remove (to fully stop charges) — review and delete manually:
   - The ECS cluster (if dedicated): aws ecs delete-cluster --cluster CLUSTER
   - The Application Load Balancer + target group (if created)
   - The ECR repository / images: aws ecr delete-repository --repository-name invforge/ai-ops --force
   - The CloudWatch Logs group: aws logs delete-log-group --log-group-name /ecs/invforge-ai-ops
   - Any WAF Web ACL + association
   - Secrets Manager secrets you created
>> Teardown of the service is complete.
EOF
