# Story 1.3 Eval Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One command runs a placeholder Eval case, prints a score per check, records the prompt and dataset versions, and exits non-zero when any score is below the stored baseline.

**Architecture:** `evals/` is a small Python package run with the backend's uv environment (`uv run --project backend python -m evals.runner` from the repo root), so later stories can import the real agent from `backend/`. Pure functions score check results and compare them with `evals/baseline.json`. A placeholder agent (a fixed function with a `PROMPT_VERSION`) stands in for the real Agent until Epic 6/7.

**Tech Stack:** Python 3.14 standard library only (`json`, `argparse`, `pathlib`, `dataclasses`), pytest 9.2.0 from the backend dev group. No new dependencies.

**Spec:** `_bmad-output/planning-artifacts/epics.md` → "Story 1.3: Eval harness with a placeholder Eval" (FR-5, AR-17). Architecture: `ARCHITECTURE-SPINE.md` AD-17 (baseline file in repo; code checks first) and AD-12 (prompts have a version id).

## Global Constraints

- `evals/` holds the runner, a dataset folder, and a baseline score file, all committed (spec AC 1).
- The command prints a score per check (FR-5). A score is the fraction of cases that passed that check: a float from 0.0 to 1.0, printed with 2 decimals.
- Any check score **below** its baseline value → exit code `1` (spec AC 2). Equal or above → `0`. No tolerance in this story (AD-17 says the tolerance is a fixed constant set later; Story 7.4 owns it).
- Every recorded result names `prompt_version` and `dataset_version` (AR-17).
- Command (from repo root, in WSL): `uv run --project backend python -m evals.runner`.
- Runner tests: `uv run --project backend pytest evals/tests`.
- Result file: `evals/results/latest.json`, git-ignored (a run output, not source).
- No AI call, no network, no database in this story. Standard library only.
- Beginner owner: one-line purpose comment at the top of each file; simple, commented code.

## Review Focus

1. **A check that is in the baseline but missing from the run** (renamed or deleted check) → must fail (exit 1), not pass silently. Test in Task 1 (`test_compare_fails_when_check_missing`).
2. **Dataset with zero cases** → must stop with a clear error and exit code `2`, not divide by zero or report 1.0. Test in Task 2 (`test_runner_rejects_empty_dataset`).
3. **A new check that has no baseline entry yet** → reported as "no baseline" and does not fail the run (the builder adds it to the baseline on purpose). Test in Task 1 (`test_compare_ignores_check_without_baseline`).
4. **Missing or broken baseline/dataset file** → exit code `2` with a message naming the file, not a raw traceback. Test in Task 2 (`test_runner_missing_baseline_file`).
5. **Running the command twice** → the result file is overwritten, never appended or duplicated. Covered by writing with mode `"w"` (Task 2 test reads one JSON object).

---

## Before Task 1

From `main`: `git checkout -b story/1-3-eval-harness`; set `1-3-eval-harness-with-a-placeholder-eval: in-progress` in `_bmad-output/implementation-artifacts/sprint-status.yaml`; add label `in-progress` to GitHub issue #3; commit the plan and the status together. Run all Python commands in WSL from the repo root.

### Task 1: Scoring and baseline comparison (pure functions)

**Files:**
- Create: `evals/__init__.py` (empty, with a one-line comment), `evals/tests/__init__.py` (empty)
- Create: `evals/scoring.py`
- Test: `evals/tests/test_scoring.py`

**Interfaces:**
- Produces:
  - `score_checks(case_results: list[dict[str, bool]]) -> dict[str, float]` — each item maps check name → passed for one case; returns check name → passed count / case count. Raises `ValueError("no cases")` for an empty list.
  - `compare_to_baseline(scores: dict[str, float], baseline: dict[str, float]) -> list[str]` — returns one failure message per problem, empty list = pass. Messages exactly: `"<check>: <score:.2f> is below baseline <base:.2f>"` and `"<check>: missing from this run (baseline <base:.2f>)"`. Checks in `scores` but not in `baseline` produce no failure.

- [ ] **Step 1: Write the failing tests** (CORE, one line each before writing):
  - `test_score_checks_fraction` — "score = share of cases that passed": `score_checks([{"a": True, "b": True}, {"a": True, "b": False}]) == {"a": 1.0, "b": 0.5}`.
  - `test_score_checks_rejects_empty` — `pytest.raises(ValueError)` for `score_checks([])`.
  - `test_compare_passes_when_equal_or_above` — `compare_to_baseline({"a": 1.0, "b": 0.6}, {"a": 1.0, "b": 0.5}) == []`.
  - `test_compare_fails_when_below` — `compare_to_baseline({"a": 0.5}, {"a": 1.0}) == ["a: 0.50 is below baseline 1.00"]`.
  - `test_compare_fails_when_check_missing` — `compare_to_baseline({}, {"a": 1.0}) == ["a: missing from this run (baseline 1.00)"]`.
  - `test_compare_ignores_check_without_baseline` — `compare_to_baseline({"new": 0.0}, {}) == []`.
- [ ] **Step 2: Run, expect FAIL** — `uv run --project backend pytest evals/tests -v` → `ModuleNotFoundError: evals.scoring`.
- [ ] **Step 3: Implement `evals/scoring.py`.**
- [ ] **Step 4: Run, expect PASS** — same command → `6 passed`.
- [ ] **Step 5: Commit** — `git commit -m "feat(evals): score checks and compare with baseline"`

### Task 2: Runner, placeholder case, baseline file

**Files:**
- Create: `evals/placeholder_agent.py`, `evals/checks.py`, `evals/runner.py`
- Create: `evals/datasets/placeholder/dataset.json`, `evals/baseline.json`, `evals/README.md`
- Modify: `.gitignore` (add `evals/results/`)
- Test: `evals/tests/test_runner.py`

**Interfaces:**
- Consumes: `score_checks`, `compare_to_baseline` (Task 1).
- Produces:
  - `placeholder_agent.PROMPT_VERSION = "placeholder-v1"`; `placeholder_agent.reply(message: str) -> str` returns `"Namaste! How can I help you today?"` for any message (a stand-in; Epic 6 replaces it).
  - `checks.CHECKS: dict[str, Callable[[dict, str], bool]]` with exactly two checks: `"reply_not_empty"` (reply has non-space text) and `"contains_expected"` (`case["expected_contains"]` is in the reply, case-insensitive). Each takes `(case, reply)`.
  - `runner.main(argv: list[str] | None = None) -> int`. Options (all with defaults relative to the `evals/` folder): `--dataset evals/datasets/placeholder/dataset.json`, `--baseline evals/baseline.json`, `--out evals/results/latest.json`. Steps: load dataset → for each case call `reply(case["message"])` and run every check → `score_checks` → load baseline → `compare_to_baseline` → print → write result → return `0` (pass), `1` (below baseline), `2` (bad input: missing/unreadable file, invalid JSON, or zero cases). Module ends with `if __name__ == "__main__": raise SystemExit(main())`.
  - Dataset file shape: `{"name": "placeholder", "version": "1", "cases": [{"id": "greeting-en", "message": "Hello", "expected_contains": "namaste"}]}`.
  - Baseline file shape: `{"dataset": "placeholder", "scores": {"reply_not_empty": 1.0, "contains_expected": 1.0}}`.
  - Result file (`--out`, parent folders created, overwritten each run): `{"prompt_version": "placeholder-v1", "dataset": "placeholder", "dataset_version": "1", "scores": {...}, "failures": [...], "passed": true|false}`.
  - Printed output (exact layout):
    ```
    Eval run: dataset placeholder v1, prompt placeholder-v1
      reply_not_empty    1.00  (baseline 1.00)
      contains_expected  1.00  (baseline 1.00)
    PASS
    ```
    A check with no baseline prints `(no baseline)`. On failure, print each failure message on its own line after the scores, then `FAIL`. Bad input prints `ERROR: <reason naming the file>` and returns 2.

- [ ] **Step 1: Write the failing tests** (CORE, one line each before writing). Use `tmp_path` for every `--out`, and for any dataset/baseline the test writes.
  - `test_runner_passes_on_placeholder` — "the real committed files pass": `main(["--out", str(tmp_path / "r.json")]) == 0`; the result JSON has `prompt_version == "placeholder-v1"`, `dataset_version == "1"`, `scores == {"reply_not_empty": 1.0, "contains_expected": 1.0}`, `passed is True`.
  - `test_runner_prints_score_per_check` — with `capsys`, output contains `"reply_not_empty    1.00"`, `"contains_expected  1.00"`, and ends with `"PASS"`.
  - `test_runner_fails_below_baseline` — "a lower score exits 1": a tmp dataset with one case whose `expected_contains` is `"booking"` → `main([...]) == 1`, output contains `"contains_expected: 0.00 is below baseline 1.00"` and `"FAIL"`, result JSON `passed is False`.
  - `test_runner_rejects_empty_dataset` — tmp dataset with `"cases": []` → returns `2`, output contains `"ERROR"`.
  - `test_runner_missing_baseline_file` — `--baseline` pointing at a missing file → returns `2`, output contains the file name.
- [ ] **Step 2: Run, expect FAIL** — `uv run --project backend pytest evals/tests -v` → import errors.
- [ ] **Step 3: Implement** the three modules and the two JSON files; add `evals/results/` to `.gitignore`.
- [ ] **Step 4: Run, expect PASS** — `uv run --project backend pytest evals/tests -v` → `11 passed`. Then the real command `uv run --project backend python -m evals.runner` prints the exact layout above and `echo $?` gives `0`. Also confirm the backend suite is untouched: `cd backend && uv run pytest -q` → 22 passed.
- [ ] **Step 5: `evals/README.md`** — what an Eval is (plain words), the two commands, what each exit code means, where the result goes, and how to change the baseline on purpose (edit `evals/baseline.json` in the same pull request, with a reason).
- [ ] **Step 6: Commit** — `git commit -m "feat(evals): runner with placeholder case and baseline"`

### Task 3: Learning notes + status

**Files:**
- Create: `docs/learning/1-3.md` (same format as `1-2.md`: what was built, why, concepts — Eval, check, score, baseline, exit code as a CI signal, prompt/dataset versions; key files tagged CORE `scoring.py`, `runner.py` / STANDARD `checks.py`, `placeholder_agent.py`, `dataset.json`, `baseline.json` / BOILERPLATE `__init__.py`, `.gitignore`; Understanding Gate placeholder)
- Modify: `docs/learning/glossary.md` (Eval, check, score, baseline, Golden Dataset, exit code, placeholder)
- Modify: `_bmad-output/implementation-artifacts/sprint-status.yaml` (`1-3-...: review`)

- [ ] **Step 1: Write the notes (STE style); set status to `review`.**
- [ ] **Step 2: Commit** — `git commit -m "docs: story 1.3 learning notes, status review"`
