# Story 1.6 Merge to Main Deploys the Demo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (CLAUDE.md: the deploy script and the deploy job are CORE → inline with checkpoints). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each merge to main whose CI passes runs migrations on Neon, then starts that commit's GHCR images on an Oracle ARM VM behind Caddy with TLS. A failed migration leaves the old version running and fails the job.

**Architecture:** One server-side script, `infra/demo/deploy.sh <sha>`, owns the deploy order: pull → `alembic upgrade head` in a one-off container of the NEW image → `docker compose up -d --wait`. If the migration fails, the script stops before `up`, so the old containers keep running. A new `deploy` job in `ci.yml` (after `build`, push to main only) copies the demo files to the VM over SSH, runs the script, and then checks the public URL for the new version. The demo stack is `infra/demo/docker-compose.yml`: Caddy (auto TLS for an sslip.io name), frontend, backend, worker, Valkey (AOF on), otel-collector → Grafana Cloud. Postgres is Neon, outside the VM.

**Tech Stack:** GitHub Actions + plain `ssh`/`scp`; Docker Engine + compose plugin on Ubuntu 24.04 aarch64 (Oracle A1.Flex); Caddy 2.11.7; Valkey 9.0; Neon Postgres 18 free; GHCR public packages; pytest text/subprocess tests (no new dependency).

**Spec:** `_bmad-output/planning-artifacts/epics.md` → "Story 1.6: Merge to main deploys the demo" (FR-3, AR-19, AR-20, AR-22, AR-24). Architecture: `ARCHITECTURE-SPINE.md` → "Deployment & environments", Cross-cutting "Migrations" and "Config" rows, Open Questions → "Oracle account tier".

## User decisions (2026-11-04)

- Oracle account: upgrade to **Pay-As-You-Go** (still $0 inside Always Free limits; idle VMs are not reclaimed). Add a budget alert.
- Domain: **sslip.io** — `DEMO_DOMAIN=<ip-with-dashes>.sslip.io` (example `140-238-1-2.sslip.io`). No DNS account.
- Accounts: user has **no Oracle and no Neon account yet** → Task 4 is a step-by-step runbook the user follows.

## Global Constraints

- Every environment runs the same images; only env vars change (AR-20). The demo compose has **no `build:`**. Images: `ghcr.io/nithinmanayilghub/sevadesk-backend:${IMAGE_TAG}` (backend AND worker) and `ghcr.io/nithinmanayilghub/sevadesk-frontend:${IMAGE_TAG}`.
- `IMAGE_TAG` is the full 40-char commit SHA. Compose reads it as `${IMAGE_TAG:?IMAGE_TAG is set by deploy.sh}`.
- Demo secrets live only in `/opt/sevadesk/.env` on the VM (mode 600), never in git (AR-19). Committed: `infra/demo/.env.example` with empty values.
- `.env` keys, exact: `DEMO_DOMAIN`, `DATABASE_URL`, `OTLP_EXPORT_ENDPOINT`, `OTLP_EXPORT_AUTH`.
- `DATABASE_URL` uses Neon's **direct** (not pooled) host, driver `postgresql+psycopg://`, and `?sslmode=require`.
- Server folder: `/opt/sevadesk/`. SSH user: `ubuntu`. Key-only SSH (Oracle default).
- GitHub environment `demo`. Secrets: `DEMO_SSH_KEY`, `DEMO_SSH_KNOWN_HOSTS`. Variables: `DEMO_HOST` (VM public IP), `DEMO_DOMAIN`.
- Deploy runs only on `push` to `main` after `build` passes. No secret is used by any PR job.
- Workflow-level `concurrency` stays as it is (`ci-${{ github.ref }}`, no cancel on main). It already runs main pushes one at a time, so two deploys never race. The deferred "per-sha concurrency group" idea is **dropped**: it would let an older run deploy after a newer one.
- AR-22: nothing on a timer touches Postgres. The demo backend healthcheck checks only that port 8000 answers; it does **not** call `/api/health` (that runs a DB query every 5 s and keeps Neon awake).
- Valkey: `--appendonly yes`, data on a named volume at `/data`. Caddy certificates on a named volume at `/data` (so restarts do not ask Let's Encrypt again).
- Every demo service has `restart: unless-stopped`.
- The backend Dockerfile `CMD` (migrate, then start) does not change. After `deploy.sh` has migrated, that start-up migration is a no-op.

## Review Focus

1. **Migration fails** (bad SQL, Neon down) → script exits non-zero, `up` never runs, old version keeps serving. Test in Task 1 (`test_failed_migration_keeps_old_version`).
2. **Deploy called without a SHA** (typo in the workflow) → exit non-zero before any `docker` call. Test in Task 1 (`test_deploy_needs_an_image_tag`).
3. **New version starts but never gets healthy** → `up --wait` fails, script fails, job fails. Test in Task 1 (`test_unhealthy_new_version_fails_deploy`).
4. **A timer that wakes Neon** (backend healthcheck hitting `/api/health`) → banned. Test in Task 2 (`test_demo_healthchecks_never_touch_the_database`).
5. **A PR (or fork PR) reaching the deploy job or its secrets** → deploy has `if:` push-to-main and `needs: build`. Test in Task 3 (`test_deploy_runs_only_on_main_after_build`).

Known limits (written in the learning note, not fixed here): if the new version fails its health wait, the old containers are already replaced (no automatic rollback); a migration that breaks the OLD code (a drop or rename) needs the expand/contract pattern, which arrives with real tables in Epic 2; SSH port 22 is open to the internet (GitHub runner IPs change), protected by key-only login.

---

## Before Task 1

From `main`: `git checkout -b story/1-6-deploy-demo`; set `1-6-merge-to-main-deploys-the-demo: in-progress` in `_bmad-output/implementation-artifacts/sprint-status.yaml`; `gh issue edit 6 --add-label in-progress`.
Record AR-24 in `ARCHITECTURE-SPINE.md`: move "Oracle account tier" out of Open Questions into "Deployment & environments" as `- Oracle account: Pay-As-You-Go (decided 2026-11-04). Still $0 inside Always Free limits; idle VMs are not reclaimed. Budget alert at $1.` and `- Demo domain: <ip-with-dashes>.sslip.io (no DNS account; changes if the VM IP changes).`
Commit this plan + status + spine (`docs: plan story 1.6, record Oracle PAYG decision`).

### Task 1: The deploy script (CORE)

**Files:**
- Create: `infra/demo/deploy.sh` (executable: `git update-index --chmod=+x`)
- Test: `backend/tests/unit/test_deploy_script.py`

**Interfaces:**
- Produces: `deploy.sh <image-tag>`. Runs from its own folder (`cd "$(dirname "$0")"`). Exports `IMAGE_TAG=<image-tag>`. Exit 0 = new version healthy. Exit 2 = no tag. Exit 1 = any other failure.

The whole algorithm (order is the point of the story):
1. `set -euo pipefail`. No argument → print `usage: deploy.sh <image-tag>` to stderr, exit 2.
2. `docker compose pull`
3. `docker compose run --rm --no-deps backend alembic upgrade head`. On failure → print `migration failed: the old version is still running` to stderr, exit 1.
4. `docker compose up -d --remove-orphans --wait --wait-timeout 180`
5. Print `deployed <image-tag>`.

Test harness: each test writes a fake `docker` script into `tmp_path/bin` and puts it first on `PATH`. The fake appends one line per call to `tmp_path/calls.log`: `IMAGE_TAG=<value> <all args>`. It exits 1 when its args contain the word in env `FAIL_ON` (empty = never fail). Run with `subprocess.run(["bash", str(DEPLOY), ...], env=..., capture_output=True, text=True)`. `DEPLOY = parents[3] / "infra" / "demo" / "deploy.sh"`.

- [ ] **Step 1: Write the failing tests** (one-line behaviour comment above each, like `test_ci_workflow.py`)

```python
def test_deploy_runs_migration_before_starting_new_version(tmp_path):
    result, calls = run_deploy(tmp_path, "abc123")
    assert result.returncode == 0
    assert calls == [
        "IMAGE_TAG=abc123 compose pull",
        "IMAGE_TAG=abc123 compose run --rm --no-deps backend alembic upgrade head",
        "IMAGE_TAG=abc123 compose up -d --remove-orphans --wait --wait-timeout 180",
    ]
    assert "deployed abc123" in result.stdout

def test_failed_migration_keeps_old_version(tmp_path):
    result, calls = run_deploy(tmp_path, "abc123", fail_on="alembic")
    assert result.returncode == 1
    assert not any(" up " in c for c in calls)
    assert "the old version is still running" in result.stderr

def test_deploy_needs_an_image_tag(tmp_path):
    result, calls = run_deploy(tmp_path)  # no tag
    assert result.returncode == 2
    assert calls == []

def test_unhealthy_new_version_fails_deploy(tmp_path):
    result, _ = run_deploy(tmp_path, "abc123", fail_on="--wait")
    assert result.returncode != 0
    assert "deployed" not in result.stdout
```

- [ ] **Step 2: Run** — WSL, from `backend/`: `uv run pytest tests/unit/test_deploy_script.py -v`. Expected: 4 FAIL (script missing).
- [ ] **Step 3: Write `infra/demo/deploy.sh`** with the algorithm above and a comment per step (why the order matters).
- [ ] **Step 4: Run** the same command. Expected: 4 PASS. Then `uv run pytest` (whole suite) passes; `uv run ruff check . && uv run ruff format --check .` from repo root are clean.
- [ ] **Step 5: Commit** `feat: deploy script migrates before starting the new version`

### Task 2: The demo stack (STANDARD)

**Files:**
- Create: `infra/demo/docker-compose.yml`, `infra/demo/Caddyfile`, `infra/demo/.env.example`
- Test: `backend/tests/unit/test_demo_compose.py`

**Interfaces:**
- Consumes: `IMAGE_TAG` from Task 1. `infra/compose/otel-collector.yaml` (reused as is; Task 3 copies it to the VM next to the compose file).
- Produces: services `caddy`, `frontend`, `backend`, `worker`, `valkey`, `otel-collector`. No `postgres`, no `lgtm`.

Shape (decisions; the implementer writes the YAML):
- A top-level `x-backend: &backend` block holds the image, `restart`, and env (`DATABASE_URL: ${DATABASE_URL:?set in .env}`, `REDIS_URL: redis://valkey:6379/0`, `OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-collector:4318`). `backend` and `worker` both use `<<: *backend`. Worker `command: ["saq", "app.worker.settings"]`.
- `backend` healthcheck: `["CMD", "python", "-c", "import socket; socket.create_connection(('localhost', 8000), 3)"]`, interval 10s, retries 12, start_period 20s. `worker` and `caddy` `depends_on` backend `service_healthy`; backend depends on valkey `service_healthy`.
- `valkey`: `command: ["valkey-server", "--appendonly", "yes"]`, volume `valkey_data:/data`, same ping healthcheck as local.
- `caddy`: image `caddy:2.11.7`, ports `80:80`, `443:443`, `443:443/udp`; volumes `./Caddyfile:/etc/caddy/Caddyfile:ro`, `caddy_data:/data`, `caddy_config:/config`; env `DEMO_DOMAIN: ${DEMO_DOMAIN:?set in .env}`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME: sevadesk-caddy`.
- `otel-collector`: same image/command as local; `OTLP_EXPORT_ENDPOINT: ${OTLP_EXPORT_ENDPOINT:?set in .env}`, `OTLP_EXPORT_AUTH: ${OTLP_EXPORT_AUTH:?set in .env}`.
- `Caddyfile`: the local file's `tracing`/`handle` body under the site address `{$DEMO_DOMAIN}` (Caddy then gets the TLS certificate and redirects http → https on its own).

- [ ] **Step 1: Write the failing tests** (text checks with a `_service_block(name)` helper, same style as `_job_block` in `test_ci_workflow.py`)

```python
def test_demo_runs_only_ghcr_images_by_tag():
    text = _text()
    assert "build:" not in text
    assert "ghcr.io/nithinmanayilghub/sevadesk-backend:${IMAGE_TAG:?" in text
    assert "ghcr.io/nithinmanayilghub/sevadesk-frontend:${IMAGE_TAG:?" in text

def test_demo_has_no_database_container():
    assert _services() == {"caddy", "frontend", "backend", "worker", "valkey", "otel-collector"}

def test_demo_valkey_keeps_jobs_across_restarts():
    block = _service_block("valkey")
    assert '"--appendonly", "yes"' in block
    assert "valkey_data:/data" in block

def test_demo_caddy_keeps_its_certificates():
    assert "caddy_data:/data" in _service_block("caddy")

def test_demo_healthchecks_never_touch_the_database():
    assert "/api/health" not in _text()

def test_every_demo_service_restarts_after_a_reboot():
    for name in _services():
        assert "restart: unless-stopped" in _service_block(name) or "<<: *backend" in _service_block(name)
    assert "restart: unless-stopped" in _anchor_block("x-backend")

def test_demo_secrets_are_not_committed():
    example = (DEMO_DIR / ".env.example").read_text(encoding="utf-8")
    for key in ("DEMO_DOMAIN", "DATABASE_URL", "OTLP_EXPORT_ENDPOINT", "OTLP_EXPORT_AUTH"):
        assert re.search(rf"^{key}=$", example, re.M)
    assert not (DEMO_DIR / ".env").exists()
```

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_demo_compose.py -v`. Expected: FAIL (files missing).
- [ ] **Step 3: Write the three files.** Add `infra/demo/.env` to `.gitignore` if the root ignore does not already cover `.env`.
- [ ] **Step 4: Run** the tests → PASS. Then `IMAGE_TAG=x DEMO_DOMAIN=x DATABASE_URL=x OTLP_EXPORT_ENDPOINT=x OTLP_EXPORT_AUTH=x docker compose -f infra/demo/docker-compose.yml config -q` → exit 0 (the file is valid compose).
- [ ] **Step 5: Commit** `feat: demo compose stack with Caddy TLS, Valkey AOF, Neon`

### Task 3: The deploy job in CI (CORE)

**Files:**
- Modify: `.github/workflows/ci.yml` (build job + new `deploy` job)
- Test: `backend/tests/unit/test_ci_workflow.py`

**Interfaces:**
- Consumes: `deploy.sh <sha>` (Task 1); files `infra/demo/docker-compose.yml`, `infra/demo/Caddyfile`, `infra/demo/deploy.sh`, `infra/compose/otel-collector.yaml` (Task 2).

Changes:
- `build`: backend image gets `build-args: APP_VERSION=${{ github.sha }}` (so `/api/v1/hello` shows the commit). Remove the `sevadesk-worker` tag (the worker runs the backend image).
- New job `deploy`: `needs: build`, `if: <PUSH_CONDITION>`, `runs-on: ubuntu-latest`, `environment: { name: demo, url: https://${{ vars.DEMO_DOMAIN }} }`, no `packages: write`. Steps:
  1. `actions/checkout@v7.0.1`
  2. Write `secrets.DEMO_SSH_KEY` to `~/.ssh/id_ed25519` (mode 600) and `secrets.DEMO_SSH_KNOWN_HOSTS` to `~/.ssh/known_hosts`. Never `StrictHostKeyChecking=no`.
  3. `scp` the four files to `ubuntu@${{ vars.DEMO_HOST }}:/opt/sevadesk/`.
  4. `ssh ubuntu@${{ vars.DEMO_HOST }} /opt/sevadesk/deploy.sh ${{ github.sha }}`
  5. Public check: `curl -fsS --retry 10 --retry-delay 6 --retry-all-errors https://${{ vars.DEMO_DOMAIN }}/api/v1/hello | jq -e --arg v "${{ github.sha }}" '.version == $v'`

- [ ] **Step 1: Write the failing tests** (and extend the existing ones)

```python
# test_ci_jobs_run_in_order: add
    assert re.search(r"^    needs: build$", _job_block("deploy"), re.M)

# test_ci_only_build_on_main_can_write_packages: loop over ("lint", "test", "eval", "deploy")

def test_deploy_runs_only_on_main_after_build():
    deploy = _job_block("deploy")
    assert f"if: {PUSH_CONDITION}" in deploy
    assert "name: demo" in deploy
    assert "StrictHostKeyChecking=no" not in _text()

def test_deploy_checks_the_public_url_for_this_commit():
    deploy = _job_block("deploy")
    assert "/opt/sevadesk/deploy.sh ${{ github.sha }}" in deploy
    assert "/api/v1/hello" in deploy and '.version == $v' in deploy

def test_images_carry_the_commit_version():
    build = _job_block("build")
    assert "APP_VERSION=${{ github.sha }}" in build
    assert "sevadesk-worker" not in _text()
```

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_ci_workflow.py -v` → new tests FAIL.
- [ ] **Step 3: Edit `ci.yml`** as above, with a comment on each step (what and why). Update the file's top comment: five jobs, `lint → test → eval → build → deploy`.
- [ ] **Step 4: Run** the tests → PASS; whole suite passes; lint clean.
- [ ] **Step 5: Commit** `feat: deploy the demo after a green build on main`

### Task 4: Accounts and server set-up (runbook; the USER does the clicks)

**Files:**
- Create: `infra/demo/README.md` — the runbook below, in short numbered steps, plus "how to deploy by hand" and "how to look at logs".

I write the runbook, then walk the user through it one part at a time, with a checkpoint after each part. Nothing secret enters the chat: the user pastes only public things (IP, `ssh-keyscan` output is public).

Parts:
1. **Oracle:** sign up (home region **India South (Hyderabad)** or **India West (Mumbai)** — permanent choice), upgrade to Pay-As-You-Go, Budgets → create a $1 monthly alert to the user's email.
2. **VM:** Compute → Instance → shape `VM.Standard.A1.Flex`, 4 OCPU, 24 GB, image Ubuntu 24.04 (aarch64), boot volume 50 GB, public IPv4, upload the user's own SSH public key. Capacity error → try another availability domain or retry later.
3. **Firewall, two layers:** VCN security list ingress TCP 80, TCP 443, UDP 443 from `0.0.0.0/0`. On the VM, Oracle's Ubuntu image has its own iptables rules: `sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT`, same for tcp 443 and udp 443, then `sudo netfilter-persistent save`.
4. **Docker:** `curl -fsSL https://get.docker.com | sudo sh`; `sudo usermod -aG docker ubuntu`; log out and in; `docker compose version` works. `sudo mkdir -p /opt/sevadesk && sudo chown ubuntu: /opt/sevadesk`.
5. **Neon:** sign up, create project `sevadesk`, Postgres 18, region = the closest to the VM region (pick from Neon's list; likely AWS Singapore). Copy the **direct** connection string. Write `/opt/sevadesk/.env` (`chmod 600`) from `.env.example`: `DEMO_DOMAIN=<ip-with-dashes>.sslip.io`, `DATABASE_URL=postgresql+psycopg://...?sslmode=require`, Grafana Cloud OTLP values — **with a NEW Grafana token** (rotate the leaked one first).
6. **Deploy key:** on the user's PC, `ssh-keygen -t ed25519 -f sevadesk-deploy -N ""`; append `sevadesk-deploy.pub` to the VM's `~/.ssh/authorized_keys`; `ssh-keyscan <ip>` → known_hosts text.
7. **GitHub:** Settings → Environments → `demo`: secrets `DEMO_SSH_KEY` (private key file content), `DEMO_SSH_KNOWN_HOSTS`; variables `DEMO_HOST`, `DEMO_DOMAIN`. Delete the local private key file after.
8. **GHCR:** make packages `sevadesk-backend` and `sevadesk-frontend` public (package settings → visibility), so the VM pulls with no login. Delete the old `sevadesk-worker` package.

- [ ] **Step 1:** write `infra/demo/README.md`; commit `docs: demo server runbook`.
- [ ] **Step 2–9:** user does parts 1–8; I check each with a command the user runs (`ssh ubuntu@<ip> docker compose version`, `curl -I http://<ip>` reaches the box, etc.).

### Task 5: Live checks (before and after merge)

- [ ] **Step 1: First deploy by hand** (images from main `5ecedb2` already exist in GHCR): `scp` the four files to `/opt/sevadesk/`, then `ssh ubuntu@<ip> /opt/sevadesk/deploy.sh <full sha of 5ecedb2>`. Expected: `deployed …`; `https://<domain>/` shows the hello page with a valid lock; `/api/v1/hello` answers (version `dev`: old images had no build-arg).
- [ ] **Step 2: Migration failure, live:** `ssh … 'DATABASE_URL=postgresql+psycopg://bad:bad@127.0.0.1:1/x?sslmode=disable /opt/sevadesk/deploy.sh <sha>'`. Expected: exit 1, "old version is still running", the site still answers.
- [ ] **Step 3: Valkey AOF:** `docker compose exec valkey valkey-cli CONFIG GET appendonly` → `yes`.
- [ ] **Step 4: Traces:** one `/api/v1/hello` call → one trace in Grafana Cloud with the 4 parts (`sevadesk-caddy`, `sevadesk-backend`, postgres span, `sevadesk-worker`).
- [ ] **Step 5: Neon sleeps (AR-22):** leave the demo idle 10 minutes; the Neon console shows the compute as Idle/Suspended. Then one page load wakes it (first request slower, still 200).

### Task 6: Learning, review, merge (DoD)

- [ ] `docs/learning/1-6.md` (what, why, concept: "migrate first, then switch"; known limits from Review Focus), glossary terms: deploy, PAYG, sslip.io, TLS certificate / Let's Encrypt, AOF, SSH key / known_hosts, GitHub environment, idle compute.
- [ ] Opus final review of the branch; fix findings with regression tests.
- [ ] Update deferred items in memory: 1.6 items done (APP_VERSION, shared image, `restart`, GHCR visibility); "worker healthcheck reading heartbeat key" → still open, move to Epic 2.
- [ ] Understanding Gate (3 questions), hands-on task, sprint-status `done` committed inside the PR.
- [ ] Open the PR; when green, `gh pr merge --merge --delete-branch`. Watch the `deploy` job on main. Expected: green; `https://<domain>/api/v1/hello` version = the merge commit SHA; GitHub shows a `demo` deployment with the URL. If it fails, fix on a new branch (main is protected). Close #6.

Test helpers in Tasks 1–2 (`run_deploy`, `_text`, `_services`, `_service_block`, `_anchor_block`) are small private functions in each test file; the implementer writes them.
