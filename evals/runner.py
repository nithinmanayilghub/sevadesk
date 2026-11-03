# The eval command: run every case, score each check, compare with the baseline, save the result.
# Run from the repo root:  uv run --project backend python -m evals.runner
# Exit codes: 0 = pass, 1 = a score is below the baseline, 2 = bad input (file missing, broken, or empty).
import argparse
import json
from pathlib import Path

from evals import placeholder_agent
from evals.checks import CHECKS
from evals.scoring import compare_to_baseline, score_checks

EVALS_DIR = Path(__file__).resolve().parent
NAME_WIDTH = 19  # column width for check names in the printed table
# Every case needs these fields: the runner sends "message", and the checks read "expected_contains".
REQUIRED_CASE_FIELDS = ("id", "message", "expected_contains")


class BadInput(Exception):
    """A dataset or baseline file is missing, broken, or empty."""


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BadInput(f"file not found: {path}")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BadInput(f"cannot read {path}: {error}")


def validate(dataset: object, dataset_path: Path, baseline: object, baseline_path: Path) -> None:
    # Check the shape of both files before we use them, so a broken file gives a clear
    # message (exit 2) instead of a crash somewhere in the middle of the run.
    if not isinstance(dataset, dict):
        raise BadInput(f"dataset must be a JSON object: {dataset_path}")
    for field in ("name", "version"):
        if not isinstance(dataset.get(field), str):
            raise BadInput(f'dataset needs a text field "{field}": {dataset_path}')
    cases = dataset.get("cases")
    if not isinstance(cases, list) or not cases:
        raise BadInput(f"dataset has no cases (cases must be a non-empty list): {dataset_path}")
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise BadInput(f"case {index} must be a JSON object: {dataset_path}")
        missing = [field for field in REQUIRED_CASE_FIELDS if not isinstance(case.get(field), str)]
        if missing:
            raise BadInput(f"case {case.get('id', index)} is missing {', '.join(missing)}: {dataset_path}")

    if not isinstance(baseline, dict) or not isinstance(baseline.get("scores"), dict):
        raise BadInput(f'baseline needs a "scores" object: {baseline_path}')
    for name, score in baseline["scores"].items():
        # bool is a kind of int in Python, so rule it out on purpose.
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise BadInput(f'baseline score for "{name}" must be a number: {baseline_path}')


def run_cases(cases: list[dict]) -> list[dict[str, bool]]:
    # For each case: ask the Agent, then run every check on its reply.
    results = []
    for case in cases:
        reply = placeholder_agent.reply(case["message"])
        results.append({name: check(case, reply) for name, check in CHECKS.items()})
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the evals and compare with the baseline.")
    parser.add_argument("--dataset", default=EVALS_DIR / "datasets" / "placeholder" / "dataset.json", type=Path)
    parser.add_argument("--baseline", default=EVALS_DIR / "baseline.json", type=Path)
    parser.add_argument("--out", default=EVALS_DIR / "results" / "latest.json", type=Path)
    args = parser.parse_args(argv)

    # Only file problems are caught here. A bug inside the Agent or a check keeps its
    # real error message, so it is never mistaken for a bad input file.
    try:
        dataset = load_json(args.dataset)
        baseline = load_json(args.baseline)
        validate(dataset, args.dataset, baseline, args.baseline)
    except BadInput as error:
        print(f"ERROR: {error}")
        return 2

    scores = score_checks(run_cases(dataset["cases"]))
    baseline_scores = baseline["scores"]
    failures = compare_to_baseline(scores, baseline_scores)

    # Print one line per check, then any failures, then PASS or FAIL.
    print(f"Eval run: dataset {dataset['name']} v{dataset['version']}, prompt {placeholder_agent.PROMPT_VERSION}")
    for name, score in scores.items():
        base = baseline_scores.get(name)
        base_text = f"(baseline {base:.2f})" if base is not None else "(no baseline)"
        print(f"  {name:<{NAME_WIDTH}}{score:.2f}  {base_text}")
    for failure in failures:
        print(failure)
    print("FAIL" if failures else "PASS")

    # Save the result. It names the prompt and dataset versions (AR-17). "w" overwrites the last run.
    result = {
        "prompt_version": placeholder_agent.PROMPT_VERSION,
        "dataset": dataset["name"],
        "dataset_version": dataset["version"],
        "scores": scores,
        "failures": failures,
        "passed": not failures,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
