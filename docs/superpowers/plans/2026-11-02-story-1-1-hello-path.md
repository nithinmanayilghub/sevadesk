# Story 1.1 — Hello Path Runs Locally Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One `docker compose up` starts Caddy, Next.js, FastAPI, Postgres 18, and Valkey 9, and `http://localhost` shows a hello value that FastAPI read from Postgres, plus the backend version.

**Architecture:** Caddy is the only public door (one origin). It sends `/api/*` to FastAPI and everything else to Next.js. FastAPI reads one row from the `app_meta` table (owned by `core`) inside a transaction that the request entry point owns (AD-15). The frontend calls the API only through a TypeScript client generated from FastAPI's OpenAPI schema (AD-14).

**Tech Stack:** Python 3.14, FastAPI 0.162.0, Uvicorn 0.54.0, SQLAlchemy 2.1.6 (sync), Alembic 1.20.1, Pydantic 2.14.2, pydantic-settings 2.16.2, psycopg 3.3.6, pytest 9.2.0, testcontainers 4.15.0, Node.js 24, Next.js 16.4.3, React 19.3.1, TypeScript 5.9.3, Tailwind CSS 4.3.3, openapi-typescript 7.13.0, openapi-fetch 0.17.0, Vitest 5.0.5, Caddy 2.11.7, Postgres 18, Valkey 9.0.

**Spec:** `_bmad-output/planning-artifacts/epics.md` — Story 1.1 (lines 250–276). Rules from `_bmad-output/planning-artifacts/architecture/architecture-seva-desk-2026-11-01/ARCHITECTURE-SPINE.md` (AD-6, AD-14, AD-15, Consistency Conventions, Stack, Structural Seed).

## Global Constraints

- Pin every version exactly as in the Stack line above (from the spine's Stack table).
- Python tooling: `uv` (manages Python 3.14, `pyproject.toml`, `uv.lock`). Node tooling: `npm` with `package-lock.json`. *(Decision made here: the spine records none.)*
- Database access: **sync** SQLAlchemy with psycopg 3 (`postgresql+psycopg://…`). *(Decision made here: simpler to read and test. Later async code, such as the SAQ worker, calls sync services through `asyncio.to_thread`.)*
- All routes live under `/api/v1`. FastAPI docs at `/api/docs`, schema at `/api/openapi.json`, so both pass through Caddy.
- One origin. No CORS middleware anywhere.
- Config only from env vars through one `pydantic-settings` object. No secrets in code, images, or `.env.example`.
- Every table has a UUIDv7 primary key (`uuid.uuid7()`, Python 3.14 stdlib). Tables are plural `snake_case`.
- Services never commit. The request entry point (`get_session` dependency) owns the one transaction.
- The frontend never hand-writes API types or calls `fetch` directly. It uses `src/api/client.ts` only.
- Exact copy: hello value in the database is `Hello from SevaDesk`. Version label on the page is `Backend version: <version>`. Error text on the page is `Could not reach the backend.`
- No worker, no Redis client, no health endpoint, no lint, no CI in this story (Stories 1.2–1.4). Valkey only has to start.
- No UI component kit yet (AR-24 leaves it to the first real UI story, 2.2).

## Review Focus

- **Missing `DATABASE_URL`:** the backend must fail at start with a clear validation error, not later on the first request. → Task 1, `test_settings_require_database_url`.
- **Backend down or returns an error:** the page must show `Could not reach the backend.`, not a blank page or a crash. → Task 3, `shows an error when the API fails`.
- **Fresh clone with no `.env` file:** `docker compose up` must still work, using safe local defaults. → Task 4, compose uses `${VAR:-default}`; verified by the smoke step.
- **Migration creates more than intended:** after `upgrade head`, only `app_meta` (plus Alembic's own `alembic_version`) exists. → Task 2, `test_migration_creates_only_app_meta`.
- **Generated API client drifts from the backend:** a changed endpoint without regenerating would break silently. → Task 3 commits `openapi.json` and `schema.d.ts`, and the Vitest test types against them. (A CI drift check belongs to Story 1.4.)

---

### Task 1: Backend project and settings

**Files:**
- Create: `backend/pyproject.toml`, `backend/uv.lock` (generated), `backend/.python-version` (`3.14`)
- Create: `backend/app/__init__.py`, `backend/app/core/__init__.py`
- Create: `backend/app/core/settings.py`
- Test: `backend/tests/unit/test_settings.py`
- Modify: `.gitignore` (add `.venv/`, `__pycache__/`, `.pytest_cache/`, `node_modules/`, `.next/`)

**Interfaces:**
- Produces: `class Settings(BaseSettings)` with fields `database_url: str` (required, env `DATABASE_URL`) and `app_version: str = "dev"` (env `APP_VERSION`). `def get_settings() -> Settings`, cached with `functools.lru_cache`; tests call `get_settings.cache_clear()`.

- [ ] **Step 1: Create the uv project.** In `backend/`: `uv init --app --name sevadesk-backend --python 3.14`, delete the sample `main.py`, then `uv add fastapi==0.162.0 uvicorn==0.54.0 sqlalchemy==2.1.6 alembic==1.20.1 pydantic==2.14.2 pydantic-settings==2.16.2 "psycopg[binary]==3.3.6"` and `uv add --dev pytest==9.2.0 "testcontainers[postgres]==4.15.0" httpx`. Add `[tool.pytest.ini_options] testpaths = ["tests"]` to `pyproject.toml`.

- [ ] **Step 2: Write the failing tests** in `backend/tests/unit/test_settings.py`:

```python
import pytest
from pydantic import ValidationError
from app.core.settings import Settings

def test_settings_read_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h:5432/d")
    monkeypatch.setenv("APP_VERSION", "1.2.3")
    s = Settings()
    assert s.database_url == "postgresql+psycopg://u:p@h:5432/d"
    assert s.app_version == "1.2.3"

def test_settings_default_version(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h:5432/d")
    monkeypatch.delenv("APP_VERSION", raising=False)
    assert Settings().app_version == "dev"

def test_settings_require_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings()
```

- [ ] **Step 3: Run and see it fail.** `uv run pytest tests/unit -v` → FAIL, `ModuleNotFoundError: app.core.settings`.

- [ ] **Step 4: Implement `Settings` and `get_settings()`** in `backend/app/core/settings.py`. Use `SettingsConfigDict(extra="ignore")`. Do not read a `.env` file (compose passes env vars).

- [ ] **Step 5: Run and see it pass.** `uv run pytest tests/unit -v` → 3 passed.

- [ ] **Step 6: Commit.** `git add .gitignore backend && git commit -m "feat(backend): add uv project and settings object"`

---

### Task 2: `app_meta` table, migration, and `GET /api/v1/hello`

**Files:**
- Create: `backend/app/core/db.py`, `backend/app/core/app_meta.py`, `backend/app/core/hello_router.py`, `backend/app/main.py`
- Create: `backend/alembic.ini`, `backend/migrations/env.py`, `backend/migrations/script.py.mako`, `backend/migrations/versions/0001_create_app_meta.py`
- Test: `backend/tests/integration/conftest.py`, `backend/tests/integration/test_hello.py`

**Interfaces:**
- Consumes: `get_settings()` from Task 1.
- Produces:
  - `db.py`: `class Base(DeclarativeBase)`; `def get_engine() -> Engine` (`lru_cache`, built from `get_settings().database_url`); `def get_session() -> Iterator[Session]` — a FastAPI dependency that opens a session, runs the request inside `session.begin()` (commit on success, rollback on error), then closes it.
  - `app_meta.py`: model `AppMeta` → table `app_meta`, columns `id: UUID` (PK, default `uuid.uuid7`), `key: str` (unique, not null), `value: str` (not null). `HELLO_KEY = "hello"`. `def get_hello_value(session: Session) -> str` (reads the row with key `hello`; uses `scalar_one()`; never commits).
  - `hello_router.py`: `router = APIRouter(prefix="/api/v1")`; `class HelloResponse(BaseModel): message: str; version: str`; `GET /hello` → `HelloResponse(message=get_hello_value(session), version=get_settings().app_version)`, `operation_id="get_hello"`.
  - `main.py`: `app = FastAPI(title="SevaDesk API", docs_url="/api/docs", openapi_url="/api/openapi.json")`, includes `hello_router.router`. No CORS middleware.

- [ ] **Step 1: Set up Alembic.** `uv run alembic init migrations`, set `script_location = migrations` in `alembic.ini`, remove the `sqlalchemy.url` line. In `migrations/env.py`, take the URL from `get_settings().database_url` and set `target_metadata = Base.metadata` (import `app.core.app_meta` so the model registers).

- [ ] **Step 2: Write migration `0001_create_app_meta.py` by hand** (`revision = "0001"`, `down_revision = None`). `upgrade()` creates `app_meta` with the three columns and a unique constraint on `key`, then `op.bulk_insert` one row: `id` = `uuid.uuid7()`, `key` = `"hello"`, `value` = `"Hello from SevaDesk"`. `downgrade()` drops the table.

- [ ] **Step 3: Write the test fixtures** in `tests/integration/conftest.py`. A session-scoped fixture starts `PostgresContainer("postgres:18", driver="psycopg")`. A function-scoped fixture `client(pg, monkeypatch)` sets `DATABASE_URL` to the container URL and `APP_VERSION=test-1`, calls `get_settings.cache_clear()` and `get_engine.cache_clear()`, runs `alembic.command.upgrade(Config("alembic.ini"), "head")`, and yields `TestClient(app)`.

- [ ] **Step 4: Write the failing tests** in `tests/integration/test_hello.py`:

```python
from sqlalchemy import inspect
from app.core.db import get_engine

def test_hello_reads_value_from_database(client):
    response = client.get("/api/v1/hello")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello from SevaDesk", "version": "test-1"}

def test_migration_creates_only_app_meta(client):
    tables = set(inspect(get_engine()).get_table_names())
    assert tables == {"alembic_version", "app_meta"}

def test_openapi_schema_lists_hello(client):
    schema = client.get("/api/openapi.json").json()
    assert "/api/v1/hello" in schema["paths"]
```

- [ ] **Step 5: Run and see it fail.** Docker Desktop must be running. `uv run pytest tests/integration -v` → FAIL (`app.main` or `app.core.db` missing).

- [ ] **Step 6: Implement** `db.py`, `app_meta.py`, `hello_router.py`, and `main.py` to the Interfaces above. Comment each file with one line on its job. In `get_session`, add a comment that names AD-15: the entry point owns the transaction; services never commit.

- [ ] **Step 7: Run and see it pass.** `uv run pytest -v` → 6 passed (3 unit, 3 integration).

- [ ] **Step 8: Commit.** `git add backend && git commit -m "feat(backend): hello endpoint reads app_meta from Postgres"`

---

### Task 3: Frontend app, generated API client, and hello card

**Files:**
- Create: `backend/app/export_openapi.py`
- Create: `frontend/` (Next.js app, `src/` directory, App Router, TypeScript, Tailwind)
- Create: `frontend/openapi.json` (generated), `frontend/src/api/schema.d.ts` (generated), `frontend/src/api/client.ts`
- Create: `frontend/src/components/HelloCard.tsx`
- Modify: `frontend/src/app/page.tsx`, `frontend/next.config.ts`, `frontend/package.json`
- Create: `frontend/vitest.config.ts`, `frontend/vitest.setup.ts`
- Test: `frontend/src/components/HelloCard.test.tsx`

**Interfaces:**
- Consumes: `app` from `backend/app/main.py` (Task 2); `GET /api/v1/hello` → `{ message: string; version: string }`.
- Produces:
  - `export_openapi.py`: `python -m app.export_openapi <out_path>` writes `json.dumps(app.openapi(), indent=2)` to the path. Needs no database.
  - `client.ts`: `export const api = createClient<paths>({ baseUrl: "" })` (relative URLs: same origin through Caddy).
  - `HelloCard` (`"use client"`): calls `api.GET("/api/v1/hello")` once on mount. While waiting it shows `Loading…`. On data it shows the message and `Backend version: <version>`. On error or a thrown network failure it shows `Could not reach the backend.`
  - `package.json` scripts: `"gen:api": "openapi-typescript openapi.json -o src/api/schema.d.ts"`, `"test": "vitest run"`.

- [ ] **Step 1: Create the Next.js app.** From the repo root: `npx create-next-app@16.4.3 frontend --ts --tailwind --app --src-dir --no-eslint --use-npm --import-alias "@/*"`. Pin `react`/`react-dom` to `19.3.1`, `typescript` to `5.9.3`, `tailwindcss` to `4.3.3`. Set `output: "standalone"` in `next.config.ts`. Replace the template `page.tsx` body with a `<main>` that renders `<HelloCard />`. Remove template images in `public/`.

- [ ] **Step 2: Add the API client tools and generate types.** `npm i openapi-fetch@0.17.0` and `npm i -D openapi-typescript@7.13.0`. Write `export_openapi.py`. Run `cd backend && uv run python -m app.export_openapi ../frontend/openapi.json`, then `cd frontend && npm run gen:api`. Expected: `src/api/schema.d.ts` contains `"/api/v1/hello"`. Write `client.ts`.

- [ ] **Step 3: Add Vitest.** `npm i -D vitest@5.0.5 @vitejs/plugin-react jsdom @testing-library/react @testing-library/jest-dom`. `vitest.config.ts`: React plugin, `environment: "jsdom"`, `setupFiles: ["./vitest.setup.ts"]`, alias `@` → `./src`. `vitest.setup.ts` imports `@testing-library/jest-dom/vitest`.

- [ ] **Step 4: Write the failing tests** in `src/components/HelloCard.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { vi, test, expect, beforeEach } from "vitest";
import { api } from "@/api/client";
import { HelloCard } from "./HelloCard";

vi.mock("@/api/client", () => ({ api: { GET: vi.fn() } }));
const GET = vi.mocked(api.GET);
beforeEach(() => GET.mockReset());

test("shows the hello value and backend version", async () => {
  GET.mockResolvedValue({ data: { message: "Hello from SevaDesk", version: "test-1" } } as never);
  render(<HelloCard />);
  expect(await screen.findByText("Hello from SevaDesk")).toBeInTheDocument();
  expect(screen.getByText("Backend version: test-1")).toBeInTheDocument();
  expect(GET).toHaveBeenCalledWith("/api/v1/hello");
});

test("shows an error when the API fails", async () => {
  GET.mockRejectedValue(new Error("network down"));
  render(<HelloCard />);
  expect(await screen.findByText("Could not reach the backend.")).toBeInTheDocument();
});

test("shows an error when the API returns an error", async () => {
  GET.mockResolvedValue({ error: { detail: "boom" } } as never);
  render(<HelloCard />);
  expect(await screen.findByText("Could not reach the backend.")).toBeInTheDocument();
});
```

- [ ] **Step 5: Run and see it fail.** `npm test` → FAIL, cannot resolve `./HelloCard`.

- [ ] **Step 6: Implement `HelloCard`** to the Interfaces above. Plain Tailwind classes only; no component kit.

- [ ] **Step 7: Run and see it pass.** `npm test` → 3 passed. Also `npm run build` → succeeds.

- [ ] **Step 8: Commit.** `git add backend/app/export_openapi.py frontend && git commit -m "feat(frontend): hello card uses generated API client"`

---

### Task 4: Docker images, compose, and Caddy — one command

**Files:**
- Create: `backend/Dockerfile`, `backend/.dockerignore`
- Create: `frontend/Dockerfile`, `frontend/.dockerignore`
- Create: `infra/compose/docker-compose.yml`, `infra/compose/Caddyfile`, `infra/compose/.env.example`
- Create: `evals/.gitkeep`, `.github/workflows/.gitkeep`, `infra/terraform/.gitkeep` (structural seed folders)

**Interfaces:**
- Consumes: backend on port 8000 (`app.main:app`), frontend standalone build on port 3000.
- Produces: services `caddy`, `frontend`, `backend`, `postgres`, `valkey`. Only `caddy` publishes a host port (`80:80`). Later stories add `worker` here.

- [ ] **Step 1: Backend image.** `python:3.14-slim`; copy `uv` from `ghcr.io/astral-sh/uv`; `uv sync --frozen --no-dev`; `ARG APP_VERSION=dev` then `ENV APP_VERSION=$APP_VERSION`. Command: `sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"`. `.dockerignore`: `.venv`, `tests`, `__pycache__`.

- [ ] **Step 2: Frontend image.** Multi-stage on `node:24-slim`: `npm ci` → `npm run build` → final stage copies `.next/standalone`, `.next/static`, `public`; runs `node server.js` with `PORT=3000`, `HOSTNAME=0.0.0.0`. `.dockerignore`: `node_modules`, `.next`.

- [ ] **Step 3: Caddyfile.** Site `:80`. `handle /api/*` → `reverse_proxy backend:8000`. `handle` (everything else) → `reverse_proxy frontend:3000`. Do not strip the `/api` prefix.

- [ ] **Step 4: docker-compose.yml.** `postgres:18` with `POSTGRES_USER/PASSWORD/DB` from `${POSTGRES_USER:-seva}` etc. and a `pg_isready` healthcheck. `valkey/valkey:9.0`. `backend` built from `../../backend`, `DATABASE_URL=postgresql+psycopg://${POSTGRES_USER:-seva}:${POSTGRES_PASSWORD:-seva}@postgres:5432/${POSTGRES_DB:-seva}`, `depends_on: postgres: condition: service_healthy`. `frontend` built from `../../frontend`. `caddy:2.11.7` mounting `./Caddyfile`, depends on `backend` and `frontend`. Named volume for Postgres data. No `env_file:` line, so a fresh clone with no `.env` works.

- [ ] **Step 5: `.env.example`.** List `POSTGRES_USER=seva`, `POSTGRES_PASSWORD=change-me-local-only`, `POSTGRES_DB=seva`, `APP_VERSION=dev`, each with a one-line comment. No real secrets.

- [ ] **Step 6: Smoke test the whole path.** From `infra/compose/`: `docker compose up --build -d`, then:
  - `curl -s http://localhost/api/v1/hello` → `{"message":"Hello from SevaDesk","version":"dev"}`
  - `curl -s -o /dev/null -w "%{http_code}" http://localhost/` → `200`
  - `curl -s http://localhost/api/docs` → contains `swagger`
  - `docker compose ps` → all five services `running` (postgres `healthy`)
  - Open `http://localhost` in a browser → shows `Hello from SevaDesk` and `Backend version: dev`.
  - `docker compose down` (keep the volume).

- [ ] **Step 7: Commit.** `git add backend/Dockerfile backend/.dockerignore frontend/Dockerfile frontend/.dockerignore infra evals .github && git commit -m "feat(infra): one-command local stack behind Caddy"`

---

### Task 5: Definition of Done — docs, learning notes, status

**Files:**
- Create: `README.md` (repo root: what SevaDesk is in two lines; "Run locally" = `cd infra/compose && docker compose up --build`; how to run backend and frontend tests; how to regenerate the API client)
- Create: `docs/learning/1-1.md`, `docs/learning/glossary.md`, `docs/learning/gaps.md`
- Modify: `_bmad-output/implementation-artifacts/sprint-status.yaml` (via the sprint script, not by hand)

- [ ] **Step 1: Write `README.md`** with the four items above. Commands must match Tasks 1–4 exactly.

- [ ] **Step 2: Write the learning notes.** `1-1.md`: what was built, why, the concept (one origin; entry point owns the transaction; generated API contract), key files. `glossary.md`: plain-word entries for reverse proxy, origin, CORS, migration, ORM, OpenAPI, transaction, env var, Testcontainers. `gaps.md`: one entry for the open gap from planning — "Why does an agent job drop its old reply when a newer Customer Message exists? (AD-7)". Add the Understanding Gate results after the gate.

- [ ] **Step 3: Run all tests once more.** `cd backend && uv run pytest -v` → 6 passed. `cd frontend && npm test` → 3 passed.

- [ ] **Step 4: Mark the story done.** Run the sprint script with `--set 1-1-hello-path-runs-locally-with-one-command=done` (same `generate` arguments as in sprint planning). Expected JSON: `"ok": true`.

- [ ] **Step 5: Commit.** `git add README.md docs/learning _bmad-output/implementation-artifacts/sprint-status.yaml && git commit -m "docs: story 1.1 readme, learning notes, status done"`
