# Scoring: turns pass/fail check results into scores, and compares the scores with the baseline.


def score_checks(case_results: list[dict[str, bool]]) -> dict[str, float]:
    """Return check name -> share of cases that passed it (0.0 to 1.0).

    Each item in case_results is one case: {check name: passed?}.
    """
    if not case_results:
        # A score from zero cases would be meaningless, so stop here.
        raise ValueError("no cases")

    passed_counts: dict[str, int] = {}
    for result in case_results:
        for check_name, passed in result.items():
            passed_counts[check_name] = passed_counts.get(check_name, 0) + (1 if passed else 0)

    total = len(case_results)
    return {name: count / total for name, count in passed_counts.items()}


def compare_to_baseline(scores: dict[str, float], baseline: dict[str, float]) -> list[str]:
    """Return one message per problem. An empty list means the run passed.

    A check that is new (in scores, not in baseline) is not a problem:
    the builder adds it to the baseline on purpose.
    """
    failures = []
    for check_name, base in baseline.items():
        if check_name not in scores:
            # The check was renamed or deleted, so we can no longer prove it holds.
            failures.append(f"{check_name}: missing from this run (baseline {base:.2f})")
        elif scores[check_name] < base:
            failures.append(f"{check_name}: {scores[check_name]:.2f} is below baseline {base:.2f}")
    return failures
