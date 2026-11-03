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


# Behaviour: the four jobs exist and each one waits for the one before it.
def test_ci_jobs_run_in_order():
    assert "needs:" not in _job_block("lint")
    assert re.search(r"^    needs: lint$", _job_block("test"), re.M)
    assert re.search(r"^    needs: test$", _job_block("eval"), re.M)
    assert re.search(r"^    needs: eval$", _job_block("build"), re.M)


# Behaviour: only the build job can write packages, and it pushes only on main.
def test_ci_only_build_on_main_can_write_packages():
    text = _text()
    top_level = text.split("\njobs:\n", 1)[0]
    assert re.search(r"^permissions:\n  contents: read$", top_level, re.M)
    assert "packages: write" not in top_level
    for job in ("lint", "test", "eval"):
        assert "packages: write" not in _job_block(job)
    build = _job_block("build")
    assert "packages: write" in build
    assert f"push: ${{{{ {PUSH_CONDITION} }}}}" in build
    assert f"if: {PUSH_CONDITION}" in build  # the ghcr.io login step
