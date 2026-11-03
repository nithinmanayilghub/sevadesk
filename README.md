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
