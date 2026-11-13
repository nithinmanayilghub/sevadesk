#!/usr/bin/env bash
# Removes ALL of AWS staging, then proves nothing billable is left. Usage: destroy.sh
# Needs the same environment variables as deploy.sh (TF_STATE_BUCKET, TF_VAR_boundary_arn, AWS credentials).
# The bootstrap stack (state bucket, budget, deployer role) is NOT touched: it must outlive every session.
set -euo pipefail

for name in TF_STATE_BUCKET TF_VAR_boundary_arn; do
  if [ -z "${!name:-}" ]; then
    echo "missing environment variable $name (see infra/terraform/README.md)" >&2
    exit 2
  fi
done

export AWS_REGION="${AWS_REGION:-ap-south-1}"
cd "$(dirname "$0")"

terraform -chdir=staging init -input=false -backend-config=bucket="$TF_STATE_BUCKET"

# image_tag is required by the config but not used to delete anything, so any value works.
terraform -chdir=staging destroy -auto-approve -input=false -var image_tag=destroy

# The proof. Its exit code (0 clean, 1 leftovers) becomes this script's exit code.
exec ./check-clean.sh
