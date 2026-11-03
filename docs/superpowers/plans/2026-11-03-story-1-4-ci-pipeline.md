# Story 1.4 CI Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every pull request runs lint + import-linter → backend, eval-runner and frontend tests (with an 80% coverage gate and a one-Alembic-head check) → the eval smoke set → a multi-arch image build, and GitHub blocks the merge when any step fails.

**Architecture:** One GitHub Actions workflow, `.github/workflows/ci.yml`, with four jobs chained by `needs:` (`lint` → `test` → `eval` → `build`). Tool config lives with the code it checks (root `ruff.toml`, `[tool.importlinter]` and `[tool.coverage]` in `backend/pyproject.toml`, `frontend/eslint.config.mjs`), so every CI command also runs locally. Branch protection on `main` (enforced for admins too) makes the four jobs required, after the repo becomes public (user decision 2026-11-03: free plan only protects public repos).

**Tech Stack:** GitHub Actions; ruff 0.17.1; import-linter 2.15; pytest-cov 7.1.0; ESLint 10.13.0 + eslint-config-next 16.4.3; uv 0.13.6; Docker Buildx + QEMU; GHCR.

**Spec:** `_bmad-output/planning-artifacts/epics.md` → "Story 1.4: CI pipeline blocks bad merges" (FR-3, AR-2, AR-5, AR-18, AR-20, NFR-10). Architecture: `ARCHITECTURE-SPINE.md` AD-2 (import-linter), Migrations convention (one head), Stack table (import-linter 2.15).

## Global Constraints

- Job order is exactly: `lint` (ruff + import-linter + ESLint + tsc) → `test` (backend + evals + frontend tests, coverage, one-head check, OpenAPI drift) → `eval` (smoke set) → `build` (images). Each later job has `needs:` on the one before (FR-3).
- A failing step blocks the merge: branch protection on `main` requires the checks `lint`, `test`, `eval`, `build`, requires a pull request, and applies to admins.
- Coverage minimum: **80%** for `backend/app` and for `evals` (user decision 2026-11-03). Below it, the test step fails (NFR-10).
- More than one Alembic head fails CI (AR-5).
- Images: backend, worker, frontend, for `linux/amd64` and `linux/arm64`, pushed to `ghcr.io/nithinmanayilghub/sevadesk-<name>:<full commit sha>` (AR-20). The worker uses the backend image (same Dockerfile, different command), so the backend build is pushed under both names: built once.
- Fork PRs get no secrets (AR-18): trigger is `pull_request` (never `pull_request_target`); top-level `permissions: contents: read`; only the `build` job on a push to `main` gets `packages: write`.
- Exact pins: Python dev deps `ruff==0.17.1`, `import-linter==2.15`, `pytest-cov==7.1.0`; npm dev deps `eslint` `10.13.0`, `eslint-config-next` `16.4.3` (matches `next` 16.4.3); uv `0.13.6` in CI and in `backend/Dockerfile` (was 0.9.7; aligns with the lock file revision); actions `actions/checkout@v7.0.1`, `actions/setup-node@v7.1.0`, `astral-sh/setup-uv@v10.3.3`, `docker/setup-qemu-action@v4.4.0`, `docker/setup-buildx-action@v4.4.1`, `docker/login-action@v4.7.0`, `docker/build-push-action@v7.4.0`. Node 22 in CI.
- Python 3.14 (from `backend/.python-version`). All Python commands locally run in WSL.
- No secrets in the repo or the workflow. GHCR login uses the built-in `GITHUB_TOKEN`.

## Review Focus

1. **A PR from a fork** → no secret and no `packages: write` reach any job. Test in Task 3 (`test_ci_workflow_never_uses_pull_request_target`, `test_ci_only_build_on_main_can_write_packages`).
2. **Someone edits a route but forgets to regenerate the frontend client** → CI fails on OpenAPI drift. Step in Task 3; proven in Task 4 by a deliberate drift on a throw-away branch.
3. **A migration whose `downgrade()` is broken** → caught by a down-and-up test, not only in production. Test in Task 2 (`test_migrations_downgrade_to_base_and_back`).
4. **The owner merges with a red check (as admin)** → GitHub still blocks it (`enforce_admins: true`). Verified in Task 4.
5. **Lint config that ignores `evals/`, or scans `node_modules`** → `ruff check .` from the repo root covers `backend/` and `evals/` and respects `.gitignore`. Verified by the Task 1 run output (file count).

---

## Before Task 1

From `main`: `git checkout -b story/1-4-ci-pipeline`; set `1-4-ci-pipeline-blocks-bad-merges: in-progress` in `sprint-status.yaml`; add label `in-progress` to issue #4; commit plan + status. Python commands run in WSL from the repo root unless a step says `cd backend`.

### Task 1: Lint and import rules (Python + frontend)

**Files:**
- Create: `ruff.toml` (repo root)
- Modify: `backend/pyproject.toml` (dev deps; `[tool.importlinter]`)
- Create: `frontend/eslint.config.mjs`; Modify: `frontend/package.json` (dev deps; scripts `lint`, `typecheck`)
- Modify: every Python file that ruff reformats or flags (style only, no behavior change)

**Interfaces:**
- Produces commands later tasks call: `uv run --project backend ruff check .`, `uv run --project backend ruff format --check .`, `cd backend && uv run lint-imports`, `cd frontend && npm run lint && npm run typecheck`.

- [ ] **Step 1: Config.**
  - `ruff.toml`: `target-version = "py314"`, `line-length = 120`, `[lint] select = ["E", "F", "W", "I", "B", "UP"]`, `[lint.isort] known-first-party = ["app", "evals"]`.
  - `uv add --dev ruff==0.17.1 import-linter==2.15` (in `backend/`).
  - `[tool.importlinter]`: `root_package = "app"`; one `forbidden` contract named "core depends on no entry point": `source_modules = ["app.core"]`, `forbidden_modules = ["app.main", "app.worker", "app.export_openapi"]` (AD-2: `core` depends on no module; `app.modules.*` gets its own contracts when modules exist).
  - Frontend: `npm install -D --save-exact eslint@10.13.0 eslint-config-next@16.4.3`; `eslint.config.mjs` exports `[...nextCoreWebVitals, ...nextTypescript, { ignores: ["src/api/schema.d.ts", ".next/**"] }]` from `eslint-config-next/core-web-vitals` and `eslint-config-next/typescript`; scripts `"lint": "eslint ."`, `"typecheck": "tsc --noEmit"`.
- [ ] **Step 2: Red.** Run all four lint commands; record each failure count (ruff will flag the known spacing in `health_router.py` and `evals/checks.py`).
- [ ] **Step 3: Fix.** `ruff format .`, then `ruff check --fix .`, then fix the rest by hand. No behavior change: no edits outside formatting, imports, and lint findings.
- [ ] **Step 4: Green.** All four lint commands exit 0. `lint-imports` prints `Contracts: 1 kept, 0 broken`. Backend `uv run pytest -q` → 22 passed; `uv run --project backend pytest evals/tests -q` → 25 passed; `npm test` → 3 passed.
- [ ] **Step 5: Prove the contract bites.** Temporarily add `import app.main` to `app/core/settings.py`, run `lint-imports` → `1 broken`; remove it. Note the output in the report.
- [ ] **Step 6: Commit** — `git commit -m "chore: ruff, import-linter and eslint with fixes"`

### Task 2: Coverage gate, one-head check, migration down test

**Files:**
- Modify: `backend/pyproject.toml` (`pytest-cov==7.1.0`; `[tool.coverage.run] source = ["app"]`, `[tool.coverage.report] fail_under = 80`, `show_missing = true`)
- Modify: `backend/alembic.ini` (`prepend_sys_path = %(here)s`, so alembic works from any folder)
- Create: `backend/tests/integration/test_migrations.py`
- Create: `evals/.coveragerc` (`[run] source = evals`, `omit = evals/tests/*`; `[report] fail_under = 80`)

**Interfaces:**
- Consumes: fixtures `pg`, `client` from `backend/tests/integration/conftest.py`; `ALEMBIC_INI` path constant there.
- Produces commands: `cd backend && uv run pytest --cov` (fails under 80%); `uv run --project backend pytest evals/tests --cov --cov-config=evals/.coveragerc`.

- [ ] **Step 1: Write the failing tests** (CORE, one line each before writing):
  - `test_alembic_has_one_head` — "the migration history never splits": `ScriptDirectory.from_config(Config(ALEMBIC_INI)).get_heads()` has length 1.
  - `test_migrations_downgrade_to_base_and_back` — "every migration can be undone": using the `client` fixture (DB at head), `command.downgrade(cfg, "base")` → table names are `{"alembic_version"}` or empty; then `command.upgrade(cfg, "head")` → `{"alembic_version", "app_meta"}` and `GET /api/v1/hello` still returns 200 with message `"Namaste from SevaDesk"`.
- [ ] **Step 2: Run, expect RED** for the reason each test exists: prove it by temporarily breaking `0002.downgrade()` (wrong SQL) → down test fails; restore. Prove the head test by temporarily adding a second migration file with `down_revision = "0001"` → head test fails; delete it.
- [ ] **Step 3: Add coverage config**; run `cd backend && uv run pytest --cov` and `uv run --project backend pytest evals/tests --cov --cov-config=evals/.coveragerc`. Expected: both report a total and pass ≥ 80%. If a total is below 80%, add tests for the uncovered lines (`show_missing` lists them), not exclusions. The only allowed exclusion is `if __name__ == "__main__":` (`exclude_also` in coverage config).
- [ ] **Step 4: Prove the gate bites**: run once with `--cov-fail-under=101` → fails with "Required test coverage of 101% not reached". Note it in the report.
- [ ] **Step 5: Commit** — `git commit -m "test: 80% coverage gate, one alembic head, migration down test"`

### Task 3: The workflow

**Files:**
- Create: `.github/workflows/ci.yml` (delete `.github/workflows/.gitkeep`)
- Modify: `backend/Dockerfile` (uv `0.9.7` → `0.13.6`)
- Create: `backend/tests/unit/test_ci_workflow.py`

**Interfaces:**
- Consumes: every command from Tasks 1–2; `uv run --project backend python -m evals.runner` (Story 1.3).
- Produces: check names `lint`, `test`, `eval`, `build` (Task 4 makes them required).

- [ ] **Step 1: Write the failing tests** (parse the YAML with a tiny loader: add `pyyaml` only if it is already in `uv.lock` as a transitive dependency; otherwise assert on the file text):
  - `test_ci_workflow_never_uses_pull_request_target` — the text has no `pull_request_target`.
  - `test_ci_jobs_run_in_order` — jobs `lint`, `test`, `eval`, `build` exist; `test` needs `lint`, `eval` needs `test`, `build` needs `eval`.
  - `test_ci_only_build_on_main_can_write_packages` — top-level permissions are `contents: read`; only `build` sets `packages: write`, and its push step is conditioned on `github.event_name == 'push' && github.ref == 'refs/heads/main'`.
- [ ] **Step 2: Run, expect FAIL** (file missing).
- [ ] **Step 3: Write `ci.yml`:**
  - `on: pull_request` (branches `[main]`) and `push` (branches `[main]`); `concurrency` group per ref with `cancel-in-progress: true`; top-level `permissions: contents: read`.
  - `lint`: checkout, setup-uv (uv 0.13.6, python from `backend/.python-version`), setup-node 22 with npm cache on `frontend/package-lock.json`, `npm ci` in frontend, the four Task 1 commands.
  - `test` (needs lint): same setup; `cd backend && uv run pytest --cov` (Testcontainers uses the runner's Docker); evals tests with coverage; frontend `npm test`; OpenAPI drift: `uv run python -m app.export_openapi ../frontend/openapi.json && cd ../frontend && npm run gen:api && git diff --exit-code -- openapi.json src/api/schema.d.ts`. (The one-head check runs inside pytest.)
  - `eval` (needs test): setup-uv; `uv run --project backend python -m evals.runner`. No secrets.
  - `build` (needs eval): `permissions: contents: read, packages: write`; QEMU + Buildx; login to `ghcr.io` with `${{ github.actor }}` / `${{ secrets.GITHUB_TOKEN }}` **only** when the push condition holds; two `build-push-action` steps: backend (context `backend`, tags `ghcr.io/nithinmanayilghub/sevadesk-backend:${{ github.sha }}` and `ghcr.io/nithinmanayilghub/sevadesk-worker:${{ github.sha }}`) and frontend (context `frontend`, tag `…/sevadesk-frontend:${{ github.sha }}`); `platforms: linux/amd64,linux/arm64`; `push:` = the push condition (PRs build without pushing); `cache-from/cache-to: type=gha` with a per-image `scope`.
  - Bump the Dockerfile uv tag to `0.13.6`.
- [ ] **Step 4: Run, expect PASS** — `cd backend && uv run pytest tests/unit/test_ci_workflow.py -v` → 3 passed; full backend suite with `--cov` passes. Local build sanity: `docker compose -f infra/compose/docker-compose.yml build backend` succeeds with uv 0.13.6.
- [ ] **Step 5: Commit** — `git commit -m "ci: lint, test, eval and multi-arch build workflow"`

### Task 4: Go live — public repo, first PR, branch protection

Outward-facing steps on GitHub; the user approved making the repo public on 2026-11-03.

- [ ] **Step 1:** `gh repo edit nithinmanayilghub/sevadesk --visibility public --accept-visibility-change-consequences`.
- [ ] **Step 2:** Push the branch; `gh pr create --base main` (title "Story 1.4: CI pipeline blocks bad merges", body with `Closes #4` — the PR merge closes the issue). Watch the run: all four jobs green. Record run URL and each job's duration in the report.
- [ ] **Step 3: Branch protection** on `main` via `gh api -X PUT repos/nithinmanayilghub/sevadesk/branches/main/protection` with: `required_status_checks: {strict: true, contexts: ["lint","test","eval","build"]}`, `enforce_admins: true`, `required_pull_request_reviews: null` (solo builder: a PR is required, an approving review is not), `restrictions: null`, plus `required_linear_history: true`. Then require PRs: if the API needs it, set `required_pull_request_reviews: {required_approving_review_count: 0}`.
- [ ] **Step 4: Prove the block** on a throw-away branch `ci-proof-red`: change one route's `operation_id` without regenerating the client, open a draft PR, confirm `test` fails on OpenAPI drift and `gh pr merge` is refused. Close the PR and delete the branch. Record the refusal message.
- [ ] **Step 5:** `README.md` "CI" section: the four jobs, how to run each locally, and the new merge flow (story branch → PR → green checks → `gh pr merge --squash`… use `--merge` to keep commits). Commit and push to the PR branch; wait for green.

### Task 5: Learning notes + status

**Files:** `docs/learning/1-4.md` (concepts: CI, pipeline/job/step, lint vs test, import contract, coverage, branch protection, fork PR secrets, multi-arch image, GHCR; key files tagged CORE `ci.yml`, `test_migrations.py` / STANDARD `ruff.toml`, `pyproject.toml` sections, `eslint.config.mjs`, `test_ci_workflow.py` / BOILERPLATE lockfiles, formatting-only diffs), `docs/learning/glossary.md`, `sprint-status.yaml` (`1-4-…: review`).

- [ ] **Step 1: Write notes (STE style); set status `review`; commit and push to the PR branch.**
