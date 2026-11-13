#!/usr/bin/env bash
# Creates (or updates) AWS staging with one version of SevaDesk. Usage: deploy.sh <image-tag>
# The tag is the full git commit SHA; CI already built and pushed GHCR images with that tag.
#
# Needs (environment variables, from the bootstrap outputs; never written in git):
#   TF_STATE_BUCKET       the S3 bucket that holds Terraform's state
#   TF_VAR_boundary_arn   the permissions boundary every staging role must carry
#   AWS credentials       laptop: AWS_PROFILE=sevadesk-staging; CI: the OIDC role
#
# Steps:
#   1. init   connect Terraform to the shared state in S3
#   2. apply  build or update everything; waits until every service is healthy (about 15 min the first time)
#   3. check  the public page must answer with THIS commit as its version
set -euo pipefail

if [ $# -lt 1 ] || [ -z "$1" ]; then
  echo "usage: deploy.sh <image-tag>" >&2
  exit 2
fi
IMAGE_TAG="$1"

# Stop early, before anything runs, if a needed value is missing.
for name in TF_STATE_BUCKET TF_VAR_boundary_arn; do
  if [ -z "${!name:-}" ]; then
    echo "missing environment variable $name (see infra/terraform/README.md)" >&2
    exit 2
  fi
done

export AWS_REGION="${AWS_REGION:-ap-south-1}"

# Run next to the staging/ folder, wherever this script is called from.
cd "$(dirname "$0")"

# 1. Connect to the shared state.
terraform -chdir=staging init -input=false -backend-config=bucket="$TF_STATE_BUCKET"

# 2. Build or update. If this fails, set -e stops the script here (exit 1).
terraform -chdir=staging apply -auto-approve -input=false -var image_tag="$IMAGE_TAG"

# 3. Check the live page. A new load balancer's name can take a few minutes to work, so retry (~5 min).
url="$(terraform -chdir=staging output -raw url)"
hello="$(curl -fsS --retry 30 --retry-delay 10 --retry-all-errors "$url/api/v1/hello")"

# The answer must contain "version": "<IMAGE_TAG>" (any spacing).
if ! grep -Eq "\"version\"[[:space:]]*:[[:space:]]*\"$IMAGE_TAG\"" <<<"$hello"; then
  echo "wrong version: expected $IMAGE_TAG, the page said: $hello" >&2
  exit 1
fi

echo "staging is live: $url"
echo "It costs money every hour. When you are done, run: infra/terraform/destroy.sh"
