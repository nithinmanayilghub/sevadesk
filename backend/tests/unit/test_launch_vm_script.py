# Tests for infra/demo/launch-vm.sh: ask Oracle for the free ARM VM until it has space.
# A fake "oci" program records each call and answers from a list, so nothing real is created.
import os
import subprocess
from pathlib import Path

# backend/tests/unit/<this file> -> parents[3] is the repo root.
LAUNCH = Path(__file__).resolve().parents[3] / "infra" / "demo" / "launch-vm.sh"

# The fake oci: log the args, then answer with line N of $OUTCOMES (N = this call's number).
# The error texts copy what the real OCI CLI prints.
FAKE_OCI = """#!/usr/bin/env bash
echo "$*" >> "$CALLS_LOG"
n=$(wc -l < "$CALLS_LOG")
case "$(sed -n "${n}p" "$OUTCOMES")" in
  ok)       echo '{"data": {"id": "ocid1.instance.fake"}}'; exit 0 ;;
  capacity) echo 'ServiceError: {"code": "InternalError", "message": "Out of host capacity."}' >&2; exit 1 ;;
  busy)     echo 'ServiceError: {"code": "TooManyRequests", "message": "Too many requests"}' >&2; exit 1 ;;
  *)        echo 'ServiceError: {"code": "NotAuthorizedOrNotFound", "message": "bad id", "status": 404}' >&2; exit 1 ;;
esac
"""

SETTINGS = {
    "COMPARTMENT_ID": "ocid1.tenancy.test",
    "AVAILABILITY_DOMAIN": "gjxL:AP-HYDERABAD-1-AD-1",
    "SUBNET_ID": "ocid1.subnet.test",
    "IMAGE_ID": "ocid1.image.test",
}


def run_launch(tmp_path: Path, outcomes: list[str], settings: dict[str, str] = SETTINGS):
    """Run launch-vm.sh with the fake oci first on PATH. Return the result and the oci calls."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "oci"
    fake.write_text(FAKE_OCI, encoding="utf-8", newline="\n")
    fake.chmod(0o755)
    (tmp_path / "outcomes").write_text("\n".join(outcomes) + "\n", encoding="utf-8", newline="\n")
    key = tmp_path / "id_ed25519.pub"
    key.write_text("ssh-ed25519 AAAA test\n", encoding="utf-8")
    calls_log = tmp_path / "calls.log"
    env = {k: v for k, v in os.environ.items() if k not in SETTINGS}
    env.update(
        PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        CALLS_LOG=str(calls_log),
        OUTCOMES=str(tmp_path / "outcomes"),
        SSH_KEY_FILE=str(key),
        WAIT_SECONDS="0",  # no real waiting in tests
        **settings,
    )
    result = subprocess.run(["bash", str(LAUNCH)], env=env, capture_output=True, text=True, timeout=30)
    calls = calls_log.read_text(encoding="utf-8").splitlines() if calls_log.exists() else []
    return result, calls


# Behaviour: "out of capacity" -> try again: big size, then smaller size, then big again.
def test_out_of_capacity_retries_both_sizes_until_success(tmp_path):
    result, calls = run_launch(tmp_path, ["capacity", "capacity", "ok"])
    assert result.returncode == 0, result.stderr
    assert len(calls) == 3
    assert '{"ocpus":4,"memoryInGBs":24}' in calls[0]
    assert '{"ocpus":2,"memoryInGBs":12}' in calls[1]
    assert '{"ocpus":4,"memoryInGBs":24}' in calls[2]
    assert "ocid1.instance.fake" in result.stdout


# Behaviour: "too many requests" (429) is also temporary, so the script tries again.
def test_too_many_requests_retries(tmp_path):
    result, calls = run_launch(tmp_path, ["busy", "ok"])
    assert result.returncode == 0, result.stderr
    assert len(calls) == 2


# Behaviour: any other error (a wrong ID, no permission) stops at once and shows Oracle's message.
def test_other_error_stops_at_once(tmp_path):
    result, calls = run_launch(tmp_path, ["bad"])
    assert result.returncode == 1
    assert len(calls) == 1
    assert "NotAuthorizedOrNotFound" in result.stderr


# Behaviour: a missing setting stops the script before it calls Oracle.
def test_missing_setting_stops_before_any_call(tmp_path):
    settings = {k: v for k, v in SETTINGS.items() if k != "SUBNET_ID"}
    result, calls = run_launch(tmp_path, ["ok"], settings)
    assert result.returncode == 2
    assert calls == []
    assert "SUBNET_ID" in result.stderr


# Behaviour: the VM gets a public IP, a 50 GB disk, our SSH key, and the name sevadesk-demo.
def test_launch_asks_for_the_demo_vm(tmp_path):
    result, calls = run_launch(tmp_path, ["ok"])
    assert result.returncode == 0, result.stderr
    call = calls[0]
    assert call.startswith("compute instance launch ")
    for part in [
        "--shape VM.Standard.A1.Flex",
        "--assign-public-ip true",
        "--boot-volume-size-in-gbs 50",
        "--display-name sevadesk-demo",
        "--subnet-id ocid1.subnet.test",
        "--image-id ocid1.image.test",
        "--compartment-id ocid1.tenancy.test",
        "--availability-domain gjxL:AP-HYDERABAD-1-AD-1",
        f"--ssh-authorized-keys-file {tmp_path / 'id_ed25519.pub'}",
    ]:
        assert part in call
