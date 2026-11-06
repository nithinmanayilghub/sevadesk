#!/usr/bin/env bash
# Ask Oracle for the free ARM VM again and again, until Oracle has space for it.
# Free ARM VMs are popular, so Oracle often answers "Out of capacity". That error is
# temporary: someone deletes a VM, and space comes back. Any other error is real: stop.
#
# Usage (WSL, after "oci setup config" works):
#   COMPARTMENT_ID=... AVAILABILITY_DOMAIN=... SUBNET_ID=... IMAGE_ID=... infra/demo/launch-vm.sh
# Leave it running. It can take hours. Ctrl+C stops it.
set -euo pipefail

# Every setting must be there before we call Oracle.
for name in COMPARTMENT_ID AVAILABILITY_DOMAIN SUBNET_ID IMAGE_ID; do
  if [ -z "${!name:-}" ]; then
    echo "missing setting: $name" >&2
    exit 2
  fi
done
SSH_KEY_FILE="${SSH_KEY_FILE:-$HOME/.ssh/id_ed25519.pub}"
WAIT_SECONDS="${WAIT_SECONDS:-60}"  # pause between rounds, so Oracle does not block us

# Sizes to try, biggest first. 4 OCPU / 24 GB is the whole free ARM allowance.
SIZES=('{"ocpus":4,"memoryInGBs":24}' '{"ocpus":2,"memoryInGBs":12}')

attempt=0
while true; do
  for size in "${SIZES[@]}"; do
    attempt=$((attempt + 1))
    echo "$(date '+%H:%M:%S') attempt $attempt: size $size"
    if output=$(oci compute instance launch \
        --compartment-id "$COMPARTMENT_ID" \
        --availability-domain "$AVAILABILITY_DOMAIN" \
        --subnet-id "$SUBNET_ID" \
        --image-id "$IMAGE_ID" \
        --shape VM.Standard.A1.Flex \
        --shape-config "$size" \
        --assign-public-ip true \
        --boot-volume-size-in-gbs 50 \
        --ssh-authorized-keys-file "$SSH_KEY_FILE" \
        --display-name sevadesk-demo 2>&1); then
      echo "$output"
      echo "VM created."
      exit 0
    fi
    # Temporary errors: no space (out of capacity) or "slow down" (429). Try again.
    if grep -qiE "out of (host )?capacity|TooManyRequests" <<<"$output"; then
      echo "  no space yet"
      continue
    fi
    # A real error (wrong ID, no permission): retrying will not help.
    echo "$output" >&2
    exit 1
  done
  sleep "$WAIT_SECONDS"
done
