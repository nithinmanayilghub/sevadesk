#!/usr/bin/env bash
# Deploys one version of SevaDesk on the demo server. Usage: deploy.sh <image-tag>
# The tag is the full git commit SHA; CI built and pushed images with that tag.
#
# The order is the whole point:
#   1. pull the new images      (nothing changes yet; the old version keeps running)
#   2. migrate the database     (with the NEW image, in a throw-away container)
#   3. start the new version    (only if the migration worked)
# If step 2 fails, we stop before step 3, so the old version is still running.
set -euo pipefail

if [ $# -lt 1 ] || [ -z "$1" ]; then
  echo "usage: deploy.sh <image-tag>" >&2
  exit 2
fi

# docker-compose.yml reads IMAGE_TAG to pick which images to run.
export IMAGE_TAG="$1"

# Run next to docker-compose.yml and .env, wherever this script is called from.
cd "$(dirname "$0")"

# 1. Download the new images. The running containers are not touched.
docker compose pull

# 2. Migrate. "run --rm --no-deps" starts one short-lived backend container from the NEW
#    image, runs alembic, then removes it. It does not touch the running containers.
if ! docker compose run --rm --no-deps backend alembic upgrade head; then
  echo "migration failed: the old version is still running" >&2
  exit 1
fi

# 3. Swap to the new version. "--wait" blocks until every container is healthy,
#    and fails (non-zero exit) if one is not healthy within 180 seconds.
docker compose up -d --remove-orphans --wait --wait-timeout 180

echo "deployed $IMAGE_TAG"
