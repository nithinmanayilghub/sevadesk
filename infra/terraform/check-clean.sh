#!/usr/bin/env bash
# Proves that no billable SevaDesk staging resource is left in AWS. Usage: check-clean.sh
# Exit 0: clean.  Exit 1: one "LEFTOVER: <id>" line per resource that still exists.
# Exit 2: an AWS question failed (no right, expired login, no network). Then we do NOT know, so never "clean".
#
# It asks each service directly about SevaDesk staging only (a name that starts with sevadesk-staging,
# or the tag Project=sevadesk). The account is shared, so other projects are never reported.
set -euo pipefail

# Git Bash on Windows turns arguments that start with / into Windows paths. Turn that off.
export MSYS_NO_PATHCONV=1

REGION="${AWS_REGION:-ap-south-1}"
leftovers=""

# Ask one question. Stop with exit 2 if AWS returns an error. Collect every ID as "<service> <id>".
ask() {
  local answer
  if ! answer="$(aws "$@" --region "$REGION" --output text)"; then
    echo "could not check: aws $1 $2 failed. Is the login (AWS_PROFILE) right and not expired?" >&2
    exit 2
  fi
  # One line per ID, with the service in front ("None" = the AWS CLI's empty answer).
  answer="${answer//$'\r'/}" # Windows AWS CLI may end lines with \r
  local id
  for id in $answer; do
    if [ "$id" != "None" ]; then
      leftovers+="$1 $id"$'\n'
    fi
  done
}

# The parts that cost money while they exist.
ask rds describe-db-instances \
  --query "DBInstances[?starts_with(DBInstanceIdentifier, 'sevadesk-staging')].DBInstanceIdentifier"
ask elasticache describe-replication-groups \
  --query "ReplicationGroups[?starts_with(ReplicationGroupId, 'sevadesk-staging')].ReplicationGroupId"
ask elbv2 describe-load-balancers \
  --query "LoadBalancers[?starts_with(LoadBalancerName, 'sevadesk-staging')].LoadBalancerName"
ask secretsmanager list-secrets \
  --query "SecretList[?starts_with(Name, 'sevadesk-staging')].Name"
# An ACTIVE cluster can still run Fargate tasks (billed per second).
ask ecs describe-clusters --clusters sevadesk-staging \
  --query "clusters[?status=='ACTIVE'].clusterName"
# Staging never makes these; if one exists with our tag, something went wrong.
ask ec2 describe-nat-gateways --filter Name=tag:Project,Values=sevadesk Name=state,Values=pending,available \
  --query "NatGateways[].NatGatewayId"
ask ec2 describe-addresses --filters Name=tag:Project,Values=sevadesk \
  --query "Addresses[].AllocationId"
# Log storage costs a little; destroy deletes the group.
ask logs describe-log-groups --log-group-name-prefix /ecs/sevadesk-staging \
  --query "logGroups[].logGroupName"

# Drop empty lines; keep each "<service> <id>" once.
found="$(grep -v -x -e '' <<<"$leftovers" | sort -u || true)"

if [ -z "$found" ]; then
  echo "clean: no billable staging resources"
  exit 0
fi

while IFS= read -r item; do
  echo "LEFTOVER: $item"
done <<<"$found"
echo "Delete these in the AWS console (region $REGION), or run destroy.sh again." >&2
exit 1
