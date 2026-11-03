# Evals

An **Eval** is an automated exam for the AI Agent. It gives the Agent fixed test messages (the **cases**), then **checks** each reply in code. Each check gets a **score**: the share of cases that passed it, from 0.00 to 1.00.

The **baseline** (`baseline.json`) holds the best scores so far. If a change makes any score drop below its baseline, the eval fails. CI will use this to block the merge (Story 1.4).

Today the Agent is a **placeholder** (`placeholder_agent.py`): it always gives the same reply. It proves the exam works before the real Agent exists (Epic 6).

## Commands

Run from the repo root, in WSL:

```
uv run --project backend python -m evals.runner     # run the evals
uv run --project backend pytest evals/tests         # test the eval runner itself
```

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Pass: every score is equal to or above its baseline |
| `1` | Fail: a score is below its baseline, or a baseline check is missing from the run |
| `2` | Bad input: a dataset or baseline file is missing, broken, or has no cases |

## Files

| File | What it holds |
|---|---|
| `runner.py` | The command: run cases, score, compare, print, save |
| `scoring.py` | Turns pass/fail results into scores; compares with the baseline |
| `checks.py` | The code checks (`reply_not_empty`, `contains_expected`) |
| `datasets/placeholder/dataset.json` | The cases, with a dataset `version` |
| `baseline.json` | The stored baseline scores |
| `results/latest.json` | The last run (not in Git). It names the prompt version and the dataset version |

## Changing the baseline

Only change `baseline.json` on purpose: for example, after you add a check or make the Agent better. Change it in the same pull request as the code, and say why in the description. Never lower a baseline only to make a failing run pass.
