# Text checks on .github/workflows/aws-staging.yml and the Terraform files: who can reach AWS, and how.
import re
from pathlib import Path

# backend/tests/unit/<this file> -> parents[3] is the repo root.
ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github" / "workflows"
AWS_WORKFLOW = WORKFLOWS / "aws-staging.yml"


def _text() -> str:
    return AWS_WORKFLOW.read_text(encoding="utf-8")


def _triggers() -> str:
    """The text of the top-level 'on:' block (up to the next top-level key)."""
    match = re.search(r"^on:\n(.*?)(?=^\S)", _text(), re.S | re.M)
    assert match, "no 'on:' block in aws-staging.yml"
    return match.group(1)


# Behaviour: AWS staging costs money, so it starts only when someone clicks "Run workflow".
def test_staging_runs_only_by_hand():
    triggers = _triggers()
    assert re.search(r"^  workflow_dispatch:", triggers, re.M)
    assert not re.search(r"^  (push|pull_request|pull_request_target|schedule|workflow_run):", triggers, re.M)


# Behaviour: the job runs in the aws-staging environment, whose protection rule waits for a human approval.
def test_staging_waits_for_approval():
    assert re.search(r"^    environment:\n      name: aws-staging$", _text(), re.M)


# Behaviour: only this workflow may ask GitHub for an AWS login token (OIDC). CI on PRs never can.
def test_only_aws_workflow_can_get_aws_tokens():
    assert "id-token: write" in _text()
    for workflow in WORKFLOWS.glob("*.y*ml"):
        if workflow.name != AWS_WORKFLOW.name:
            assert "id-token" not in workflow.read_text(encoding="utf-8"), workflow.name


# Behaviour: no long-lived AWS keys are stored in GitHub, and the account ID is hidden in the public logs.
def test_staging_uses_no_stored_aws_keys():
    for workflow in WORKFLOWS.glob("*.y*ml"):
        text = workflow.read_text(encoding="utf-8")
        assert "aws-access-key-id" not in text, workflow.name
        assert "AWS_SECRET_ACCESS_KEY" not in text, workflow.name
    assert "role-to-assume: ${{ secrets.AWS_ROLE_ARN }}" in _text()
    assert "mask-aws-account-id: true" in _text()


# Behaviour: CI runs the very same scripts as the laptop (one way to deploy, one way to destroy).
def test_staging_calls_the_same_scripts():
    text = _text()
    assert "infra/terraform/deploy.sh" in text
    assert "infra/terraform/destroy.sh" in text


# Behaviour: no NAT gateway anywhere (it costs about $1 per day, even when idle).
def test_no_nat_gateway_in_terraform():
    for tf in (ROOT / "infra" / "terraform").rglob("*.tf"):
        assert "aws_nat_gateway" not in tf.read_text(encoding="utf-8"), tf.name
