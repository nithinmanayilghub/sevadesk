# Story 1.2 Health Checks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `GET /api/health` and `GET /api/health/worker` tell an operator at once when Postgres, Valkey, or the SAQ worker is down.

**Architecture:** One `core` error envelope (`AppError` + one exception handler) turns failures into `{"error": {"code", "message"}}`. `core/health.py` holds small check functions (Postgres `SELECT 1`, Valkey `PING`, heartbeat key exists). The SAQ worker (`app/worker.py`) runs a cron job every 10 s that sets a Valkey key with a 30 s TTL; Valkey deletes the key by itself when the worker stops, so "key exists" means "heartbeat in the last 30 s".

**Tech Stack:** FastAPI 0.162.0, SQLAlchemy 2.1.6 + psycopg 3.3.6, redis-py 7.4.1, SAQ 0.26.5, Valkey 9.0, Testcontainers 4.15.0.

**Spec:** `_bmad-output/planning-artifacts/epics.md` → "Story 1.2: Health checks for the API and the worker" (FR-2, AR-3, AR-9). Architecture: `_bmad-output/planning-artifacts/architecture/architecture-seva-desk-2026-11-01/ARCHITECTURE-SPINE.md` (Errors convention, AD-6, AD-3 Redis key rule, Stack table).

## Global Constraints

- Health paths are exactly `/api/health` and `/api/health/worker` (AR-9). They are not under `/api/v1`: they are operator endpoints, not product API.
- Error body is exactly `{"error": {"code": "<code>", "message": "<message>"}}` (AR-3). Errors are "typed exceptions mapped once in `core`".
- Config through env vars and the one `Settings` object only. New var: `REDIS_URL` (required). No secrets in code.
- Exact pins: `redis==7.4.1`, `saq[redis]==0.26.5`, `httpx2==2.16.0` (replaces `httpx`; Starlette 1.10 deprecates `httpx` in its TestClient).
- Redis keys start with their purpose (AD-3). Heartbeat key: `health:worker:heartbeat`. It is global (no `business_id`): the worker is not tenant data.
- Heartbeat: written every 10 s, TTL 30 s.
- Each dependency check must give up after 2 s, so a hung dependency gives 503, not a hung request.
- Integration tests use real containers: `postgres:18` and `valkey/valkey:9.0`.
- Core file naming (deferred from 1.1, decided here): `core` is not a feature module, so it uses flat topic files: `<topic>.py` for logic and `<topic>_router.py` for routes (same as `hello_router.py`). The `router.py`/`service.py`/`models.py` convention applies inside `app/modules/<name>/`.

## Review Focus

1. **Both Postgres and Valkey down** → 503 that names both (`message` lists `database` and `redis`). Test in Task 2.
2. **A dependency hangs instead of refusing** → the check stops after 2 s and returns 503. Pinned by the timeout settings in Task 2 (`connect_timeout=2`, `socket_timeout=2`), checked by a unit test on the client options.
3. **Postgres comes back after an outage** → the next `/api/health` returns 200 (no dead pooled connection). `pool_pre_ping=True` on the engine; Task 2 test calls health with a bad URL, then a good one.
4. **Heartbeat key without TTL** (a bug sets it forever) → a dead worker would look alive. Task 3 test asserts `0 < ttl <= 30`.
5. **Worker endpoint when Valkey itself is down** → 503 with code `dependency_unavailable` naming `redis`, not a 500 crash. Test in Task 3.

## Before Task 1

From `main`: `git checkout -b story/1-2-health-checks`; set `1-2-health-checks-for-the-api-and-the-worker: in-progress` in `_bmad-output/implementation-artifacts/sprint-status.yaml`; commit the plan and the status together. Run backend tests from WSL (`backend/.venv` is the WSL one).

---

### Task 1: Error envelope + test-tooling cleanup

**Files:**
- Create: `backend/app/core/errors.py`
- Modify: `backend/app/main.py` (register the handler)
- Modify: `backend/pyproject.toml` (description; `httpx` → `httpx2==2.16.0`)
- Modify: `backend/tests/integration/conftest.py` (import from `testcontainers.community.postgres`; `get_engine().dispose()` after each test)
- Test: `backend/tests/unit/test_errors.py`

**Interfaces:**
- Produces: `class AppError(Exception)` with `__init__(self, code: str, message: str, status_code: int)`, attributes `code`, `message`, `status_code`. `def register_error_handlers(app: FastAPI) -> None`.

- [ ] **Step 1: Write the failing test** (CORE: "an AppError raised in a route becomes the one error envelope with its status code")

```python
def test_app_error_becomes_envelope():
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom")
    def boom():
        raise AppError(code="dependency_unavailable", message="database is not reachable", status_code=503)

    response = TestClient(app).get("/boom")
    assert response.status_code == 503
    assert response.json() == {"error": {"code": "dependency_unavailable", "message": "database is not reachable"}}
```

- [ ] **Step 2: Run it, expect FAIL** — `uv run pytest tests/unit/test_errors.py -v` → `ModuleNotFoundError: app.core.errors`.
- [ ] **Step 3: Implement `errors.py`** — handler is `app.add_exception_handler(AppError, ...)` returning `JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})`. Call `register_error_handlers(app)` in `main.py`.
- [ ] **Step 4: Tooling cleanup** — in `pyproject.toml` set `description = "SevaDesk backend: FastAPI API and SAQ worker"`; replace `httpx>=0.28.1` with `httpx2==2.16.0`; run `uv sync`. In `conftest.py` change the import to `from testcontainers.community.postgres import PostgresContainer`; in the `client` fixture, after `yield`, call `get_engine().dispose()`.
- [ ] **Step 5: Run all tests, expect PASS and no `DeprecationWarning` for httpx or testcontainers** — `uv run pytest` → `8 passed`.
- [ ] **Step 6: Commit** — `git commit -m "feat(core): one error envelope; clean test deprecations"`

### Task 2: `GET /api/health` (Postgres + Valkey)

**Files:**
- Modify: `backend/app/core/settings.py` (add `redis_url: str`, required)
- Modify: `backend/app/core/db.py` (`create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 2})`)
- Create: `backend/app/core/redis_client.py`
- Create: `backend/app/core/health.py`
- Create: `backend/app/core/health_router.py`
- Modify: `backend/app/main.py` (include the router)
- Modify: `backend/tests/integration/conftest.py` (session-scoped Valkey container; `client` sets `REDIS_URL`)
- Modify: `backend/tests/unit/test_settings.py` (every test that builds `Settings` also sets `REDIS_URL`; add a "requires REDIS_URL" test)
- Test: `backend/tests/integration/test_health.py`, `backend/tests/unit/test_redis_client.py`

**Interfaces:**
- Consumes: `AppError` (Task 1).
- Produces:
  - `redis_client.get_redis() -> redis.Redis` — `@lru_cache`, `redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=2, socket_timeout=2)`.
  - `health.check_database() -> bool` — runs `SELECT 1` on `get_engine()`; returns `False` on any `SQLAlchemyError`.
  - `health.check_redis() -> bool` — `get_redis().ping()`; returns `False` on any `redis.RedisError`.
  - `health_router.router` — `APIRouter(prefix="/api/health")`, route `GET ""` with `operation_id="get_health"`.
  - Response model `HealthResponse(status: str, database: str, redis: str)`; 200 body `{"status": "ok", "database": "ok", "redis": "ok"}`.
  - 503: `AppError(code="dependency_unavailable", message="Not reachable: " + ", ".join(failing), status_code=503)`, where `failing` is the ordered list of names from `["database", "redis"]` that failed.
- Test fixtures produced (later tasks use them): `valkey` (session-scoped `ValkeyContainer("valkey/valkey:9.0")`); `redis_url(valkey) -> str` builds `f"redis://{valkey.get_host()}:{valkey.get_exposed_port()}/0"` (redis-py does not accept the `valkey://` scheme). `client` also does `monkeypatch.setenv("REDIS_URL", redis_url)` and `get_redis.cache_clear()`.
- Unreachable URLs for 503 tests: `DATABASE_URL=postgresql+psycopg://x:x@127.0.0.1:1/x`, `REDIS_URL=redis://127.0.0.1:1/0` (port 1 refuses at once). Set them with `monkeypatch`, then clear the caches (`get_settings`, `get_engine`, `get_redis`).

- [ ] **Step 1: Write the failing tests** (CORE, one line each before writing):
  - `test_health_ok` — "both reachable → 200 and each dependency says ok": status 200, body `{"status": "ok", "database": "ok", "redis": "ok"}`.
  - `test_health_database_down` — "Postgres unreachable → 503 envelope naming database": 503, body `{"error": {"code": "dependency_unavailable", "message": "Not reachable: database"}}`.
  - `test_health_redis_down` — same with Redis: message `"Not reachable: redis"`.
  - `test_health_both_down` — message `"Not reachable: database, redis"`.
  - `test_health_recovers_after_database_returns` — call with the bad DB URL (503), then restore the good URL and clear caches, call again → 200.
  - `test_openapi_lists_health` — `"/api/health" in schema["paths"]`.
  - Unit `test_redis_client_has_timeouts` — with `REDIS_URL=redis://localhost:6379/0`, `get_redis().connection_pool.connection_kwargs` has `socket_connect_timeout == 2` and `socket_timeout == 2`.
- [ ] **Step 2: Run, expect FAIL** — `uv run pytest tests/integration/test_health.py tests/unit/test_redis_client.py -v` → 404s / import errors.
- [ ] **Step 3: Add pins** — `uv add redis==7.4.1`.
- [ ] **Step 4: Implement** settings field, engine options, `redis_client.py`, `health.py`, `health_router.py`; include the router in `main.py`. Fix the fixtures and `test_settings.py` as listed above.
- [ ] **Step 5: Run all tests, expect PASS** — `uv run pytest` → all pass (8 old + 8 new = 16).
- [ ] **Step 6: Regenerate the frontend client** — `uv run python -m app.export_openapi ../frontend/openapi.json`, then `cd ../frontend && npm run gen:api && npm test` → 3 passed. Commit the changed `openapi.json` and `src/api/schema.d.ts`.
- [ ] **Step 7: Commit** — `git commit -m "feat(core): GET /api/health checks Postgres and Valkey"`

### Task 3: Worker heartbeat + `GET /api/health/worker`

**Files:**
- Create: `backend/app/worker.py`
- Modify: `backend/app/core/health.py` (heartbeat constants + `check_worker_heartbeat`)
- Modify: `backend/app/core/health_router.py` (route `GET /worker`)
- Test: `backend/tests/integration/test_worker_health.py`

**Interfaces:**
- Consumes: `get_redis`, `AppError`, fixtures `valkey`, `redis_url`, `client` (Task 2).
- Produces:
  - `health.HEARTBEAT_KEY = "health:worker:heartbeat"`, `health.HEARTBEAT_TTL_SECONDS = 30`.
  - `health.check_worker_heartbeat() -> bool` — `get_redis().exists(HEARTBEAT_KEY) == 1`; raises nothing: a `redis.RedisError` propagates to the route, which turns it into the 503 below.
  - `worker.write_heartbeat(ctx: dict) -> None` (async) — `await ctx["redis"].set(HEARTBEAT_KEY, <UTC ISO time string>, ex=HEARTBEAT_TTL_SECONDS)`.
  - `worker.startup(ctx)` puts `redis.asyncio.Redis.from_url(get_settings().redis_url)` in `ctx["redis"]`; `worker.shutdown(ctx)` closes it with `aclose()`.
  - `worker.settings = {"queue": Queue.from_url(get_settings().redis_url), "functions": [], "cron_jobs": [CronJob(write_heartbeat, cron="* * * * * */10")], "startup": startup, "shutdown": shutdown}` (SAQ's 6th cron field is seconds). Run with `saq app.worker.settings`.
  - Route `GET /api/health/worker`, `operation_id="get_worker_health"`: 200 `{"status": "ok"}` (model `WorkerHealthResponse(status: str)`); no heartbeat → 503 `AppError(code="worker_unavailable", message="No worker heartbeat in the last 30 seconds", status_code=503)`; Redis error → 503 `AppError(code="dependency_unavailable", message="Not reachable: redis", status_code=503)`.

- [ ] **Step 1: Write the failing tests** (CORE, one line each before writing):
  - `test_worker_health_ok_after_heartbeat` — "a heartbeat written by the worker makes the endpoint 200": `asyncio.run(write_heartbeat({"redis": redis.asyncio.Redis.from_url(redis_url)}))`, then GET → 200, `{"status": "ok"}`.
  - `test_worker_health_503_without_heartbeat` — delete the key first; GET → 503, code `worker_unavailable`.
  - `test_heartbeat_has_ttl` — after `write_heartbeat`, `0 < get_redis().ttl(HEARTBEAT_KEY) <= 30`.
  - `test_worker_health_503_when_redis_down` — bad `REDIS_URL` → 503, `{"error": {"code": "dependency_unavailable", "message": "Not reachable: redis"}}`.
  - `test_worker_settings_schedule_heartbeat` — `worker.settings["cron_jobs"][0].function is write_heartbeat` and its `cron == "* * * * * */10"`.
  - Each test that writes the key deletes it at the end, so tests do not leak state (the Valkey container is shared).
- [ ] **Step 2: Run, expect FAIL** — `uv run pytest tests/integration/test_worker_health.py -v`.
- [ ] **Step 3: Add pin** — `uv add "saq[redis]==0.26.5"`.
- [ ] **Step 4: Implement** `worker.py`, the heartbeat check, and the route.
- [ ] **Step 5: Run all tests, expect PASS** — `uv run pytest` → 21 passed. Regenerate the frontend client again (Task 2 Step 6).
- [ ] **Step 6: Commit** — `git commit -m "feat: SAQ worker heartbeat and GET /api/health/worker"`

### Task 4: Compose: worker container + readiness

**Files:**
- Modify: `infra/compose/docker-compose.yml`
- Modify: `README.md` (health endpoints + how to see a 503)

**Interfaces:**
- Consumes: `saq app.worker.settings` (Task 3), `/api/health` (Task 2).

- [ ] **Step 1: Edit compose:**
  - `valkey`: add `healthcheck: test: ["CMD", "valkey-cli", "ping"]`, `interval: 5s`, `timeout: 3s`, `retries: 10`.
  - `backend`: add env `REDIS_URL: redis://valkey:6379/0`; `depends_on` adds `valkey: condition: service_healthy`; add `healthcheck` using `["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=3)"]`, `interval: 5s`, `timeout: 5s`, `retries: 20`, `start_period: 10s`.
  - New `worker` service: same `build` as backend, `command: ["saq", "app.worker.settings"]`, env `DATABASE_URL` and `REDIS_URL` (same values as backend), `depends_on: backend: condition: service_healthy` (backend runs the migrations first).
  - `caddy`: `depends_on` uses `backend: condition: service_healthy` (closes the 1.1 deferred readiness item).
- [ ] **Step 2: Verify the stack** — `docker compose -f infra/compose/docker-compose.yml up --build -d`; wait for healthy; then:
  - `curl -s http://localhost/api/health` → `{"status":"ok","database":"ok","redis":"ok"}`
  - `curl -s http://localhost/api/health/worker` → `{"status":"ok"}` (within 10 s of the worker start)
  - `docker compose ... stop worker`, wait 35 s, `curl -si http://localhost/api/health/worker` → `503` with `worker_unavailable`. Then `start worker`.
  - `docker compose ... stop valkey`, `curl -si http://localhost/api/health` → `503` naming `redis`. Then `start valkey`.
- [ ] **Step 3: README** — add a "Health checks" section: the two URLs, what 200 and 503 mean, and the stop-worker check above.
- [ ] **Step 4: Commit** — `git commit -m "feat(infra): worker container, Valkey and backend healthchecks"`

### Task 5: Learning notes + status

**Files:**
- Create: `docs/learning/1-2.md` (what was built, why, concepts: health vs readiness, TTL heartbeat, error envelope, dependency timeouts; key files)
- Modify: `docs/learning/glossary.md` (health check, readiness, heartbeat, TTL, cron, SAQ, Valkey/Redis, error envelope, 503)
- Modify: `_bmad-output/implementation-artifacts/sprint-status.yaml` (`1-2-...: review`)

- [ ] **Step 1: Write the notes; set status to `review`.**
- [ ] **Step 2: Commit** — `git commit -m "docs: story 1.2 learning notes, status review"`
