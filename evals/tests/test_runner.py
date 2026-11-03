# Tests for evals/runner.py: the eval command end to end, with the real files and with temporary ones.
import json

import pytest

from evals import runner
from evals.runner import main


def write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_runner_passes_on_placeholder(tmp_path):
    # Behaviour: the committed dataset and baseline pass, and the result names both versions (AR-17).
    out = tmp_path / "r.json"
    assert main(["--out", str(out)]) == 0
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["prompt_version"] == "placeholder-v1"
    assert result["dataset_version"] == "1"
    assert result["scores"] == {"reply_not_empty": 1.0, "contains_expected": 1.0}
    assert result["passed"] is True


def test_runner_prints_score_per_check(tmp_path, capsys):
    # Behaviour: one score line per check, then PASS (FR-5).
    main(["--out", str(tmp_path / "r.json")])
    output = capsys.readouterr().out
    assert "reply_not_empty    1.00" in output
    assert "contains_expected  1.00" in output
    assert output.strip().endswith("PASS")


def test_runner_fails_below_baseline(tmp_path, capsys):
    # Behaviour: a score below the baseline exits 1, so CI can fail on it.
    dataset = write_json(tmp_path / "d.json", {
        "name": "placeholder", "version": "1",
        "cases": [{"id": "x", "message": "Hello", "expected_contains": "booking"}],
    })
    out = tmp_path / "r.json"
    assert main(["--dataset", dataset, "--out", str(out)]) == 1
    output = capsys.readouterr().out
    assert "contains_expected: 0.00 is below baseline 1.00" in output
    assert "FAIL" in output
    assert json.loads(out.read_text(encoding="utf-8"))["passed"] is False


def test_runner_rejects_empty_dataset(tmp_path, capsys):
    # Behaviour: zero cases is bad input (exit 2), not a fake pass.
    dataset = write_json(tmp_path / "d.json", {"name": "placeholder", "version": "1", "cases": []})
    assert main(["--dataset", dataset, "--out", str(tmp_path / "r.json")]) == 2
    assert "ERROR" in capsys.readouterr().out


GOOD_DATASET = {
    "name": "placeholder", "version": "1",
    "cases": [{"id": "greeting-en", "message": "Hello", "expected_contains": "namaste"}],
}
GOOD_BASELINE = {"dataset": "placeholder", "scores": {"reply_not_empty": 1.0, "contains_expected": 1.0}}


@pytest.mark.parametrize(
    "which, content",
    [
        ("baseline", {"scores": {"reply_not_empty": "high"}}),  # score is not a number
        ("baseline", {"scores": ["reply_not_empty"]}),  # scores is not an object
        ("baseline", {"dataset": "placeholder"}),  # scores is missing
        ("dataset", ["not", "an", "object"]),  # dataset is a list
        ("dataset", {"name": "placeholder", "cases": GOOD_DATASET["cases"]}),  # version is missing
        ("dataset", {"name": "placeholder", "version": "1", "cases": "Hello"}),  # cases is not a list
        ("dataset", {"name": "placeholder", "version": "1", "cases": [{"id": "x", "message": "Hello"}]}),  # case field missing
    ],
)
def test_runner_rejects_malformed_file(tmp_path, capsys, which, content):
    # Behaviour: a file with the wrong shape is bad input (exit 2) and the message names the file, never a crash.
    files = {"dataset": GOOD_DATASET, "baseline": GOOD_BASELINE}
    files[which] = content
    dataset = write_json(tmp_path / "my_dataset.json", files["dataset"])
    baseline = write_json(tmp_path / "my_baseline.json", files["baseline"])
    code = main(["--dataset", dataset, "--baseline", baseline, "--out", str(tmp_path / "r.json")])
    output = capsys.readouterr().out
    assert code == 2
    assert "ERROR" in output
    assert f"my_{which}.json" in output


def test_runner_rejects_broken_json(tmp_path, capsys):
    # Behaviour: a file that is not valid JSON is bad input (exit 2) and names the file.
    dataset = tmp_path / "broken.json"
    dataset.write_text("{not json", encoding="utf-8")
    assert main(["--dataset", str(dataset), "--out", str(tmp_path / "r.json")]) == 2
    assert "broken.json" in capsys.readouterr().out


def test_runner_rejects_non_utf8_file(tmp_path, capsys):
    # Behaviour: a file that is not UTF-8 text is bad input (exit 2), not a crash.
    dataset = tmp_path / "latin.json"
    dataset.write_bytes(b'{"name": "caf\xe9"}')
    assert main(["--dataset", str(dataset), "--out", str(tmp_path / "r.json")]) == 2
    assert "latin.json" in capsys.readouterr().out


def test_runner_missing_dataset_file(tmp_path, capsys):
    # Behaviour: a missing dataset file is bad input (exit 2) and names the file.
    assert main(["--dataset", str(tmp_path / "gone.json"), "--out", str(tmp_path / "r.json")]) == 2
    assert "gone.json" in capsys.readouterr().out


def test_runner_new_check_without_baseline(tmp_path, capsys):
    # Behaviour: a check with no baseline entry prints "(no baseline)" and does not fail the run.
    baseline = write_json(tmp_path / "b.json", {"scores": {"reply_not_empty": 1.0}})
    assert main(["--baseline", baseline, "--out", str(tmp_path / "r.json")]) == 0
    assert "contains_expected  1.00  (no baseline)" in capsys.readouterr().out


def test_runner_overwrites_result_file(tmp_path):
    # Behaviour: a second run replaces the result file; it still holds exactly one JSON object.
    out = tmp_path / "r.json"
    main(["--out", str(out)])
    main(["--out", str(out)])
    assert json.loads(out.read_text(encoding="utf-8"))["passed"] is True


def test_runner_does_not_hide_check_bugs(tmp_path, monkeypatch):
    # Behaviour: a bug inside a check keeps its real error; it is not reported as a bad input file.
    def broken_check(case, reply):
        return case["no_such_field"]

    monkeypatch.setitem(runner.CHECKS, "broken", broken_check)
    with pytest.raises(KeyError):
        main(["--out", str(tmp_path / "r.json")])


def test_runner_missing_baseline_file(tmp_path, capsys):
    # Behaviour: a missing baseline file is bad input (exit 2), and the message names the file.
    missing = tmp_path / "no_such_baseline.json"
    assert main(["--baseline", str(missing), "--out", str(tmp_path / "r.json")]) == 2
    assert "no_such_baseline.json" in capsys.readouterr().out
