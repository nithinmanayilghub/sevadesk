# Tests for evals/runner.py: the eval command end to end, with the real files and with temporary ones.
import json

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


def test_runner_missing_baseline_file(tmp_path, capsys):
    # Behaviour: a missing baseline file is bad input (exit 2), and the message names the file.
    missing = tmp_path / "no_such_baseline.json"
    assert main(["--baseline", str(missing), "--out", str(tmp_path / "r.json")]) == 2
    assert "no_such_baseline.json" in capsys.readouterr().out
