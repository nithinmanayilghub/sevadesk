# Text checks on .github/workflows/ci.yml: job order and the safety rules for fork PRs.
import re
from pathlib import Path

# backend/tests/unit/<this file> -> parents[3] is the repo root.
WORKFLOW = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "ci.yml"
PUSH_CONDITION = "github.event_name == 'push' && github.ref == 'refs/heads/main'"


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _job_block(job: str) -> str:
    """Return the text of one job: from '  <job>:' to the next job (or end of file)."""
    jobs_part = _text().split("\njobs:\n", 1)[1]
    match = re.search(rf"^  {job}:\n(.*?)(?=^  \w[\w-]*:\n|\Z)", jobs_part, re.S | re.M)
    assert match, f"job '{job}' not found in ci.yml"
    return match.group(1)


# Behaviour: fork PRs must never run with secrets, so the risky trigger is banned.
def test_ci_workflow_never_uses_pull_request_target():
    assert "pull_request_target" not in _text()


# Behaviour: the five jobs exist and each one waits for the one before it.
def test_ci_jobs_run_in_order():
    assert "needs:" not in _job_block("lint")
    assert re.search(r"^    needs: lint$", _job_block("test"), re.M)
    assert re.search(r"^    needs: test$", _job_block("eval"), re.M)
    assert re.search(r"^    needs: eval$", _job_block("build"), re.M)
    assert re.search(r"^    needs: build$", _job_block("deploy"), re.M)


# Behaviour: only the build job can write packages, and it pushes only on main.
def test_ci_only_build_on_main_can_write_packages():
    text = _text()
    top_level = text.split("\njobs:\n", 1)[0]
    assert re.search(r"^permissions:\n  contents: read$", top_level, re.M)
    assert "packages: write" not in top_level
    for job in ("lint", "test", "eval", "deploy"):
        assert "packages: write" not in _job_block(job)
    build = _job_block("build")
    assert "packages: write" in build
    assert build.count(f"push: ${{{{ {PUSH_CONDITION} }}}}") == 2
    assert f"if: {PUSH_CONDITION}" in build  # the ghcr.io login step


# Behaviour: every setup-uv step pins Python 3.14 with a real input (not an ignored one).
def test_ci_pins_python_version():
    text = _text()
    assert "python-version-file" not in text
    assert text.count('python-version: "3.14"') == text.count("astral-sh/setup-uv@") == 3


# Behaviour: only a push to main, after a green build, can deploy. PRs never reach the secrets.
def test_deploy_runs_only_on_main_after_build():
    deploy = _job_block("deploy")
    assert f"if: {PUSH_CONDITION}" in deploy
    assert "name: demo" in deploy
    # SSH must check the server's identity (known_hosts); never skip that check.
    assert "StrictHostKeyChecking=no" not in _text()


# Behaviour: the job deploys this exact commit, then checks the public URL reports it.
def test_deploy_checks_the_public_url_for_this_commit():
    deploy = _job_block("deploy")
    assert "/opt/sevadesk/deploy.sh ${{ github.sha }}" in deploy
    assert "/api/v1/hello" in deploy
    assert ".version == $v" in deploy


# Behaviour: every PR checks the Terraform files (format, validate, and the mock tests of both stacks).
def test_lint_runs_terraform_tests():
    lint = _job_block("lint")
    assert "hashicorp/setup-terraform@" in lint
    assert "terraform fmt -check -recursive infra/terraform" in lint
    for stack in ("bootstrap", "staging"):
        assert f"-chdir=infra/terraform/{stack} init -backend=false" in lint
        assert f"-chdir=infra/terraform/{stack} validate" in lint
        assert f"-chdir=infra/terraform/{stack} test" in lint


# Behaviour: the backend image reports its commit as its version; the worker reuses that image.
def test_images_carry_the_commit_version():
    assert "APP_VERSION=${{ github.sha }}" in _job_block("build")
    assert "sevadesk-worker" not in _text()
