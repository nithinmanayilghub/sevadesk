# Tests for infra/demo/deploy.sh: the order of deploy steps, and what happens when one fails.
# A fake "docker" program records each call, so no real containers run.
import os
import subprocess
from pathlib import Path

# backend/tests/unit/<this file> -> parents[3] is the repo root.
DEPLOY = Path(__file__).resolve().parents[3] / "infra" / "demo" / "deploy.sh"

# The fake docker: log "IMAGE_TAG=<value> <args>", then fail if the args contain $FAIL_ON.
FAKE_DOCKER = """#!/usr/bin/env bash
echo "IMAGE_TAG=${IMAGE_TAG:-} $*" >> "$CALLS_LOG"
if [ -n "${FAIL_ON:-}" ] && [[ " $* " == *" $FAIL_ON "* ]]; then
  exit 1
fi
exit 0
"""


def run_deploy(tmp_path: Path, *args: str, fail_on: str = "") -> tuple[subprocess.CompletedProcess, list[str]]:
    """Run deploy.sh with the fake docker first on PATH. Return the result and the docker calls."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "docker"
    fake.write_text(FAKE_DOCKER, encoding="utf-8", newline="\n")
    fake.chmod(0o755)
    calls_log = tmp_path / "calls.log"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "CALLS_LOG": str(calls_log),
        "FAIL_ON": fail_on,
    }
    env.pop("IMAGE_TAG", None)  # only deploy.sh may set it
    result = subprocess.run(["bash", str(DEPLOY), *args], env=env, capture_output=True, text=True)
    calls = calls_log.read_text(encoding="utf-8").splitlines() if calls_log.exists() else []
    return result, calls


# Behaviour: pull, then migrate with the NEW image, then start the new version. In that order.
def test_deploy_runs_migration_before_starting_new_version(tmp_path):
    result, calls = run_deploy(tmp_path, "abc123")
    assert result.returncode == 0, result.stderr
    assert calls == [
        "IMAGE_TAG=abc123 compose pull",
        "IMAGE_TAG=abc123 compose run --rm --no-deps backend alembic upgrade head",
        "IMAGE_TAG=abc123 compose up -d --remove-orphans --wait --wait-timeout 180",
        "IMAGE_TAG=abc123 image prune -f",
    ]
    assert "deployed abc123" in result.stdout


# Behaviour: a failed migration stops the deploy before "up", so the old version keeps running.
def test_failed_migration_keeps_old_version(tmp_path):
    result, calls = run_deploy(tmp_path, "abc123", fail_on="alembic")
    assert result.returncode == 1
    assert not any(" up " in call for call in calls)
    assert "the old version is still running" in result.stderr


# Behaviour: no image tag means a usage error before any docker command runs.
def test_deploy_needs_an_image_tag(tmp_path):
    result, calls = run_deploy(tmp_path)
    assert result.returncode == 2
    assert calls == []
    assert "usage: deploy.sh <image-tag>" in result.stderr


# Behaviour: if the new version never gets healthy, "up --wait" fails and so does the deploy.
def test_unhealthy_new_version_fails_deploy(tmp_path):
    result, calls = run_deploy(tmp_path, "abc123", fail_on="--wait")
    assert calls[-1].startswith("IMAGE_TAG=abc123 compose up")  # it got as far as "up"
    assert result.returncode == 1
    assert "deployed" not in result.stdout
