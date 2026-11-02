# SevaDesk

SevaDesk is a multi-tenant SaaS (many businesses share one app) for Indian home-service businesses.
Story 1.1 gives us a "hello path": browser, then Caddy, then FastAPI, then Postgres.

## Run locally

You need Docker Desktop running.

```bash
cd infra/compose
docker compose up --build
```

Then open http://localhost. API docs live at http://localhost/api/docs.

## Run the tests

Backend (needs Docker Desktop, because tests start a real Postgres 18 with Testcontainers):

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

Do this after you change the backend API. First export the API description. Then generate the TypeScript types.

```bash
cd backend
uv run python -m app.export_openapi ../frontend/openapi.json
cd ../frontend
npm run gen:api
```
