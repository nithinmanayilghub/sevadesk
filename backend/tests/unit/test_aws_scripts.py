# Tests for infra/terraform/deploy.sh, destroy.sh and check-clean.sh.
# Fake "terraform", "aws" and "curl" programs record each call, so nothing real runs and nothing costs money.
import os
import subprocess
from pathlib import Path

# backend/tests/unit/<this file> -> parents[3] is the repo root.
SCRIPTS = Path(__file__).resolve().parents[3] / "infra" / "terraform"

# Each fake logs "<name> <args>", fails if its args contain $FAIL_ON, and prints a canned answer.
FAKE_TERRAFORM = """#!/usr/bin/env bash
echo "terraform $*" >> "$CALLS_LOG"
if [ -n "${FAIL_ON:-}" ] && [[ " $* " == *" $FAIL_ON "* ]]; then exit 1; fi
if [[ " $* " == *" output "* ]]; then printf '%s' "$FAKE_URL"; fi
exit 0
"""

# The aws fake answers by service (and for ec2 by command): FAKE_AWS_<NAME>, e.g. FAKE_AWS_RDS.
# Unset means an empty answer; the real CLI prints "None" for that, which tests also use.
# It fails (exit 254, like the real CLI on AccessDenied) if its args contain $FAIL_ON.
FAKE_AWS = """#!/usr/bin/env bash
echo "aws $*" >> "$CALLS_LOG"
if [ -n "${FAIL_ON:-}" ] && [[ " $* " == *" $FAIL_ON "* ]]; then
  echo "An error occurred (AccessDeniedException)" >&2
  exit 254
fi
case "$1 $2" in
  rds\\ *) printf '%s\\n' "${FAKE_AWS_RDS:-}" ;;
  elasticache\\ *) printf '%s\\n' "${FAKE_AWS_ELASTICACHE:-}" ;;
  elbv2\\ *) printf '%s\\n' "${FAKE_AWS_ALB:-}" ;;
  secretsmanager\\ *) printf '%s\\n' "${FAKE_AWS_SECRET:-}" ;;
  ecs\\ *) printf '%s\\n' "${FAKE_AWS_ECS:-}" ;;
  logs\\ *) printf '%s\\n' "${FAKE_AWS_LOGS:-}" ;;
  "ec2 describe-nat-gateways") printf '%s\\n' "${FAKE_AWS_NAT:-}" ;;
  "ec2 describe-addresses") printf '%s\\n' "${FAKE_AWS_EIP:-}" ;;
esac
exit 0
"""

FAKE_CURL = """#!/usr/bin/env bash
echo "curl $*" >> "$CALLS_LOG"
printf '%s' "$FAKE_HELLO"
exit 0
"""

SHA = "abc123"


def run_script(tmp_path: Path, script: str, *args: str, **env_overrides: str):
    """Run one script with the fakes first on PATH. Return (result, list of recorded calls)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in {"terraform": FAKE_TERRAFORM, "aws": FAKE_AWS, "curl": FAKE_CURL}.items():
        fake = bin_dir / name
        fake.write_text(body, encoding="utf-8", newline="\n")
        fake.chmod(0o755)
    calls_log = tmp_path / "calls.log"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "CALLS_LOG": str(calls_log),
        "TF_STATE_BUCKET": "test-bucket",
        "TF_VAR_boundary_arn": "arn:aws:iam::111122223333:policy/sevadesk-staging-boundary",
        "FAKE_URL": "http://fake-alb",
        "FAKE_HELLO": f'{{"message": "hello", "version": "{SHA}"}}',
        "CHECK_CLEAN_ATTEMPTS": "1",  # no waiting between checks in tests
        "CHECK_CLEAN_DELAY": "0",
    }
    env.update(env_overrides)
    env = {key: value for key, value in env.items() if value is not None}
    result = subprocess.run(["bash", str(SCRIPTS / script), *args], env=env, capture_output=True, text=True)
    calls = calls_log.read_text(encoding="utf-8").splitlines() if calls_log.exists() else []
    return result, calls


def without(name: str) -> dict:
    """Env override that removes one variable."""
    return {name: None}


# Behaviour: no image tag means a usage error before anything runs.
def test_deploy_needs_an_image_tag(tmp_path):
    result, calls = run_script(tmp_path, "deploy.sh")
    assert result.returncode == 2
    assert calls == []
    assert "usage: deploy.sh <image-tag>" in result.stderr


# Behaviour: without the state bucket, Terraform would lose its memory, so stop before anything runs.
def test_deploy_needs_the_state_bucket(tmp_path):
    result, calls = run_script(tmp_path, "deploy.sh", SHA, **without("TF_STATE_BUCKET"))
    assert result.returncode == 2
    assert calls == []
    assert "TF_STATE_BUCKET" in result.stderr


# Behaviour: without the boundary ARN, the roles could not be created, so stop before anything runs.
def test_deploy_needs_the_boundary(tmp_path):
    result, calls = run_script(tmp_path, "deploy.sh", SHA, **without("TF_VAR_boundary_arn"))
    assert result.returncode == 2
    assert calls == []
    assert "TF_VAR_boundary_arn" in result.stderr


# Behaviour: init with the shared state, build this commit, read the URL, then check the live page. In that order.
def test_deploy_order(tmp_path):
    result, calls = run_script(tmp_path, "deploy.sh", SHA)
    assert result.returncode == 0, result.stderr
    assert calls == [
        "terraform -chdir=staging init -input=false -backend-config=bucket=test-bucket",
        f"terraform -chdir=staging apply -auto-approve -input=false -var image_tag={SHA}",
        "terraform -chdir=staging output -raw url",
        "curl -fsS --retry 30 --retry-delay 10 --retry-all-errors http://fake-alb/api/v1/hello",
    ]
    assert "staging is live: http://fake-alb" in result.stdout


# Behaviour: if Terraform fails, the deploy fails and never claims the page is live.
def test_failed_apply_stops_before_check(tmp_path):
    result, calls = run_script(tmp_path, "deploy.sh", SHA, FAIL_ON="apply")
    assert result.returncode == 1
    assert not any(call.startswith("curl") for call in calls)
    assert "staging is live" not in result.stdout


# Behaviour: a page that answers with another version means the deploy did not work.
def test_deploy_fails_when_version_differs(tmp_path):
    result, _ = run_script(tmp_path, "deploy.sh", SHA, FAKE_HELLO='{"version": "old"}')
    assert result.returncode == 1
    assert SHA in result.stderr
    assert "old" in result.stderr


# Behaviour: the version check does not care about JSON spacing (FastAPI sends no spaces).
def test_deploy_accepts_compact_json(tmp_path):
    result, _ = run_script(tmp_path, "deploy.sh", SHA, FAKE_HELLO=f'{{"message":"hello","version":"{SHA}"}}')
    assert result.returncode == 0, result.stderr


# Behaviour: destroy removes everything, then proves nothing billable is left.
def test_destroy_then_checks_clean(tmp_path):
    result, calls = run_script(tmp_path, "destroy.sh")
    assert result.returncode == 0, result.stderr
    assert calls[0] == "terraform -chdir=staging init -input=false -backend-config=bucket=test-bucket"
    assert calls[1] == "terraform -chdir=staging destroy -auto-approve -input=false -var image_tag=destroy"
    assert any(call.startswith("aws rds") for call in calls[2:])
    assert "clean: no billable staging resources" in result.stdout


# Behaviour: if Terraform destroy fails, the destroy fails (no false "clean").
def test_failed_destroy_fails(tmp_path):
    result, calls = run_script(tmp_path, "destroy.sh", FAIL_ON="destroy")
    assert result.returncode == 1
    assert not any(call.startswith("aws") for call in calls)


# Behaviour: no leftovers -> exit 0 and say so ("None" is what the AWS CLI prints for an empty answer).
def test_check_clean_passes_when_empty(tmp_path):
    result, _ = run_script(tmp_path, "check-clean.sh", FAKE_AWS_RDS="None", FAKE_AWS_ALB="None")
    assert result.returncode == 0, result.stderr
    assert "clean: no billable staging resources" in result.stdout


# Behaviour: a leftover database is named, and the check fails.
def test_check_clean_reports_leftovers(tmp_path):
    result, _ = run_script(tmp_path, "check-clean.sh", FAKE_AWS_RDS="sevadesk-staging-db")
    assert result.returncode == 1
    assert "LEFTOVER: rds sevadesk-staging-db" in result.stdout


# Behaviour: every kind of billable leftover is found and listed, not only the first one.
def test_check_clean_lists_every_leftover(tmp_path):
    result, _ = run_script(
        tmp_path,
        "check-clean.sh",
        FAKE_AWS_RDS="sevadesk-staging-db",
        FAKE_AWS_ELASTICACHE="sevadesk-staging-cache",
        FAKE_AWS_ALB="sevadesk-staging",
        FAKE_AWS_SECRET="sevadesk-staging/database-url",
        FAKE_AWS_ECS="sevadesk-staging",
        FAKE_AWS_NAT="nat-0abc",
        FAKE_AWS_LOGS="/ecs/sevadesk-staging",
        FAKE_AWS_EIP="eipalloc-0abc",
    )
    assert result.returncode == 1
    assert result.stdout.count("LEFTOVER:") == 8


# Behaviour (regression, review 2026-11-13): if an AWS call fails (no right, expired login, no network),
# the check must FAIL. It must never say "clean" after it could not look.
def test_check_clean_fails_loudly_when_aws_fails(tmp_path):
    result, _ = run_script(tmp_path, "check-clean.sh", FAIL_ON="elbv2")
    assert result.returncode == 2
    assert "clean:" not in result.stdout
    assert "could not check" in result.stderr


# Behaviour: the account is shared, so every question names SevaDesk staging (by name or by tag),
# and it asks in Mumbai.
def test_check_clean_only_looks_at_sevadesk(tmp_path):
    _, calls = run_script(tmp_path, "check-clean.sh")
    aws_calls = [call for call in calls if call.startswith("aws")]
    assert len(aws_calls) == 8
    for call in aws_calls:
        assert "sevadesk" in call, call
        assert "--region ap-south-1" in call, call
