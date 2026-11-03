# Unit tests for evals/scoring.py: turning check results into scores and comparing with the baseline.
import pytest

from evals.scoring import compare_to_baseline, score_checks


def test_score_checks_fraction():
    # Behaviour: a score is the share of cases that passed that check.
    results = [{"a": True, "b": True}, {"a": True, "b": False}]
    assert score_checks(results) == {"a": 1.0, "b": 0.5}


def test_score_checks_rejects_empty():
    # Behaviour: zero cases is an error, never a fake score.
    with pytest.raises(ValueError):
        score_checks([])


def test_compare_passes_when_equal_or_above():
    # Behaviour: equal to or above the baseline is a pass (no failures).
    assert compare_to_baseline({"a": 1.0, "b": 0.6}, {"a": 1.0, "b": 0.5}) == []


def test_compare_fails_when_below():
    # Behaviour: any score below its baseline is a failure with a clear message.
    assert compare_to_baseline({"a": 0.5}, {"a": 1.0}) == ["a: 0.50 is below baseline 1.00"]


def test_compare_fails_when_check_missing():
    # Behaviour: a check in the baseline but not in this run fails (it was renamed or deleted).
    assert compare_to_baseline({}, {"a": 1.0}) == ["a: missing from this run (baseline 1.00)"]


def test_compare_ignores_check_without_baseline():
    # Behaviour: a new check with no baseline yet does not fail the run.
    assert compare_to_baseline({"new": 0.0}, {}) == []
