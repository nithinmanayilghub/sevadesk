# SevaDesk

SevaDesk is a multi-tenant SaaS (many businesses share one app) for Indian home-service businesses.
Story 1.1 builds a "hello path": the smallest request that touches every layer. It goes from the browser to Caddy (the front door that sends each request to the right server), then to FastAPI (the Python web framework that runs our API), then to Postgres (the database), and back.

## Run locally

You need Docker Desktop running. Docker runs each part of the app in its own sealed box (a container), so you do not install them by hand.

```bash
cd infra/compose
docker compose up --build
```

Then open http://localhost. API docs live at http://localhost/api/docs.

## Run the tests

Backend (needs Docker Desktop, because tests use Testcontainers, a tool that starts a real Postgres 18 database in a container just for the test):

```bash
cd backend
uv run pytest
```

Frontend:

```bash
cd frontend
npm test
```

## Regenerate the API client

Do this after you change the backend API. First export the API description. Then generate the TypeScript types (a typed description of what the API sends and accepts, so the frontend catches mistakes early).

```bash
cd backend
uv run python -m app.export_openapi ../frontend/openapi.json
cd ../frontend
npm run gen:api
```

## Health checks

Two URLs tell you if the stack is alive:

- `GET http://localhost/api/health` checks Postgres and Valkey.
- `GET http://localhost/api/health/worker` checks the background worker (it must have sent a heartbeat in the last 30 seconds).

`200` means all good. `503` means something is down; the body's `code` says what kind of failure it is, and its `message` names the part (for example `Not reachable: redis`).

See a 503 yourself:

```bash
docker compose -f infra/compose/docker-compose.yml stop worker
# wait about 35 seconds
curl -si http://localhost/api/health/worker   # 503 worker_unavailable
docker compose -f infra/compose/docker-compose.yml start worker
```

Same idea with `stop valkey` and `/api/health` (503 naming `redis`).

## CI (checks on every pull request)

GitHub Actions runs `.github/workflows/ci.yml` on every pull request to `main`, and again after each merge. The four jobs run in order. If one fails, the later jobs do not run, and GitHub blocks the merge.

| Job | What it checks | Run it yourself (WSL, repo root) |
|---|---|---|
| `lint` | Python style (ruff), module import rules (import-linter), frontend style and types | `uv run --project backend ruff check .` · `uv run --project backend ruff format --check .` · `cd backend && uv run lint-imports` · `cd frontend && npm run lint && npm run typecheck` |
| `test` | All tests, coverage ≥ 80%, one Alembic head, migrations undo cleanly, API client matches the API | `cd backend && uv run pytest --cov` · `uv run --project backend pytest evals/tests --cov --cov-config=evals/.coveragerc` · `cd frontend && npm test` |
| `eval` | The AI quality score is not below the baseline | `uv run --project backend python -m evals.runner` |
| `build` | Docker images build for `amd64` and `arm64`; on `main` they are pushed to `ghcr.io/nithinmanayilghub/sevadesk-*` | `docker compose -f infra/compose/docker-compose.yml build` |

Fix style problems automatically with `uv run --project backend ruff format .` and `uv run --project backend ruff check --fix .`.

**How a story reaches `main`:** nobody can push to `main` directly, not even the owner. Push the story branch, open a pull request, wait for four green checks, then merge:

```bash
git push -u origin story/<id>
gh pr create --base main --fill
gh pr checks --watch
gh pr merge --merge --delete-branch
```

## Observability (logs and traces)

Every request makes one trace (a tree of timed steps for one request): Caddy → FastAPI → Postgres → the worker job. Every backend and worker log line is JSON with a `request_id` and a `trace_id`. Phone numbers and address fields are masked by `backend/app/core/masking.py` before anything leaves the app.

Where the data goes:

```
backend, worker, Caddy  →  otel-collector  →  local Grafana (default)  or  Grafana Cloud
```

- Local: open http://localhost (to make a trace), then http://localhost:3001 → Explore → **Tempo** → Search → service `sevadesk-caddy`. Logs are under **Loki**.
- Grafana Cloud: set `OTLP_EXPORT_ENDPOINT` and `OTLP_EXPORT_AUTH` in `infra/compose/.env` (see `.env.example`), then restart only the collector: `docker compose up -d otel-collector`. No code changes.
- Backend logs in the terminal: `docker compose logs backend worker --tail 20`.
