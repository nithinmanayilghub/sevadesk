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


class BadInput(Exception):
    """A dataset or baseline file is missing, broken, or empty."""


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BadInput(f"file not found: {path}")
    except (OSError, json.JSONDecodeError) as error:
        raise BadInput(f"cannot read {path}: {error}")


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

    try:
        dataset = load_json(args.dataset)
        baseline = load_json(args.baseline)
        cases = dataset.get("cases") or []
        if not cases:
            raise BadInput(f"dataset has no cases: {args.dataset}")
        scores = score_checks(run_cases(cases))
        baseline_scores = baseline["scores"]
    except KeyError as error:
        print(f"ERROR: missing field {error} in the dataset or baseline file")
        return 2
    except BadInput as error:
        print(f"ERROR: {error}")
        return 2

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
