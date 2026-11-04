# Story 1.5 One Trace Across the Whole Request — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (CLAUDE.md: CORE-heavy story → inline with checkpoints). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One `GET /api/v1/hello` makes one trace (Caddy → FastAPI → Postgres → worker job), every backend/worker log line is JSON with a request ID and a trace ID, and one `core` masking function hides Indian phone numbers and address fields in logs, spans, and exports.

**Architecture:** `core/masking.py` owns the one `mask()` function. `core/telemetry.py` owns OpenTelemetry setup: a JSON log formatter, a masking log filter, a request-ID middleware, and a masking span exporter that wraps **every** exporter (so no export path skips masking). `core/jobs.py` captures `traceparent` + `request_id` inside the request and enqueues after the response (so after the commit, AD-15). The worker continues the trace from `traceparent`. All apps send OTLP to one OpenTelemetry Collector container; the collector forwards to a local Grafana (`grafana/otel-lgtm`) by default, or to Grafana Cloud when two env vars change. Caddy makes the first ("frontend request") span with its built-in `tracing` directive (user decision 2026-11-03: Caddy, not a browser SDK).

**Tech Stack:** opentelemetry-sdk 1.45.2, opentelemetry-exporter-otlp-proto-http 1.45.2, opentelemetry-instrumentation-fastapi 0.66b2, opentelemetry-instrumentation-sqlalchemy 0.66b2; SAQ 0.26.5; Caddy 2.11.7 `tracing`; `otel/opentelemetry-collector-contrib:0.163.2`; `grafana/otel-lgtm:0.39.0`.

**Spec:** `_bmad-output/planning-artifacts/epics.md` → "Story 1.5: One trace across the whole request" (FR-4, AR-11, NFR-8). Architecture: `ARCHITECTURE-SPINE.md` AD-7 (job carries `traceparent`), AD-13 (one masking function), AD-15 (enqueue after commit), Stack table (opentelemetry-sdk 1.45.2), Cross-cutting "Logging" row.

## Global Constraints

- Only OpenTelemetry APIs in app code. No vendor SDK (Grafana, Datadog, Sentry, …) and no vendor URL in `backend/app/`. The destination changes by env vars only (`OTEL_EXPORTER_OTLP_ENDPOINT` for apps; `OTLP_EXPORT_ENDPOINT` + `OTLP_EXPORT_AUTH` for the collector).
- No export at all when `OTEL_EXPORTER_OTLP_ENDPOINT` is unset (tests and CI send nothing).
- One masking function: `app.core.masking.mask`. Logs, span attributes, span event attributes, and exported log records all pass through it. No second masking rule anywhere.
- Masked placeholders, exact: phone → `[PHONE]`; address field value → `[MASKED]`.
- Log line fields, exact names: `timestamp` (ISO 8601 UTC), `level`, `logger`, `message`, `request_id`, `trace_id` (32 lowercase hex or `null`), `span_id` (16 lowercase hex or `null`), plus masked extras. `request_id` is `null` outside a request or job.
- Response header `X-Request-ID` on every API response (32 lowercase hex, `uuid4().hex`). The backend always generates it; it never trusts a client-sent value.
- Service names: `sevadesk-caddy`, `sevadesk-backend`, `sevadesk-worker`.
- Job name constant `TRACE_PING_JOB = "trace_ping"`. Payload keys: `traceparent`, `request_id`.
- Enqueue only after the response is sent (FastAPI `BackgroundTasks`), so after the DB commit (AD-15). An enqueue failure is logged and never changes the `/hello` response.
- Secrets (Grafana Cloud token) live in `infra/compose/.env` only, never in git.
- Python commands run in WSL from `backend/` (`uv run pytest …`).

## Review Focus

1. **A phone number written with spaces, hyphens, `+91`, or Devanagari digits** (`+91 98765-43210`, `०९८७६५४३२१०`) → masked. Test in Task 1 (`test_mask_phone_formats`).
2. **A log written from a child logger** (`logging.getLogger("app.x")`) → still masked; filters on a logger do not run for propagated records, so the filter sits on the handlers. Test in Task 2 (`test_child_logger_message_is_masked`).
3. **A phone number in a span attribute or in an exception event** → masked before any exporter sees it. Test in Task 3 (`test_span_attributes_and_events_are_masked`).
4. **Valkey down while `/hello` runs** → `/hello` still returns 200 and an `enqueue failed` error is logged. Test in Task 4 (`test_hello_still_ok_when_enqueue_fails`).
5. **Uvicorn access logs** (not our code) → also JSON with the masking filter. Test in Task 2 (`test_uvicorn_loggers_use_root_json_handler`).

Known limits (not fixed here, written in the learning note): Caddy's own span is not masked by our function (its attributes are method, route, status, no body); names and free-text addresses inside a message are not detected (only fields named like `address`).

---

## Before Task 1

From `main`: `git checkout -b story/1-5-one-trace`; set `1-5-one-trace-across-the-whole-request: in-progress` in `_bmad-output/implementation-artifacts/sprint-status.yaml`; `gh issue edit 5 --add-label in-progress`; commit this plan + status (`docs: plan story 1.5`).

### Task 1: The one masking function (CORE)

**Files:**
- Create: `backend/app/core/masking.py`
- Test: `backend/tests/unit/test_masking.py`

**Interfaces:**
- Produces: `mask(value: object, key: str | None = None) -> object`; constants `PHONE_PLACEHOLDER = "[PHONE]"`, `FIELD_PLACEHOLDER = "[MASKED]"`.

Rules (the whole algorithm):
- If `key` contains `"address"` (case-insensitive) and `value` is not `None` → `FIELD_PLACEHOLDER`.
- `str` → replace each phone match with `PHONE_PLACEHOLDER`. Phone = an optional `+`, then 10 to 13 digits, with at most one space or hyphen between digits, not touching another digit. Digits are `0-9` and Devanagari `०-९` (U+0966–U+096F), written as explicit classes (do not rely on `\d`).
- `dict` → new dict, each value masked with its own key. `list`/`tuple` → same type, items masked with the parent `key`.
- Anything else → returned unchanged.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("text", [
    "call 9876543210 now", "call +91 98765 43210 now", "call +91-98765-43210 now",
    "call 098765 43210 now", "call 080-2345-6789 now", "call ९८७६५४३२१० now", "call +९१ ९८७६५ ४३२१० now",
])
def test_mask_phone_formats(text):
    assert mask(text) == "call [PHONE] now"

@pytest.mark.parametrize("text", ["4 items", "year 2026", "pin 560001", "date 2026-11-03", "id 12345678"])
def test_mask_leaves_short_numbers(text):
    assert mask(text) == text

def test_mask_address_field_by_key():
    assert mask("12 MG Road", key="address") == "[MASKED]"
    assert mask("12 MG Road", key="customer.home_address") == "[MASKED]"
    assert mask(None, key="address") is None

def test_mask_nested_structures():
    data = {"address": "12 MG Road", "notes": ["ring 9876543210"], "count": 3}
    assert mask(data) == {"address": "[MASKED]", "notes": ["ring [PHONE]"], "count": 3}
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest tests/unit/test_masking.py -v` → `ModuleNotFoundError: app.core.masking`.
- [ ] **Step 3: Implement `mask` in `app/core/masking.py`** with one compiled regex and the rules above. Comment each part of the regex.
- [ ] **Step 4: Run, expect PASS** (same command).
- [ ] **Step 5: Commit** — `feat: add core masking for phone numbers and address fields`.

### Task 2: JSON logs with request ID and trace ID (CORE)

**Files:**
- Create: `backend/app/core/telemetry.py` (logging part)
- Modify: `backend/pyproject.toml`, `backend/uv.lock` (add `opentelemetry-sdk==1.45.2`, `opentelemetry-exporter-otlp-proto-http==1.45.2`, `opentelemetry-instrumentation-fastapi==0.66b2`, `opentelemetry-instrumentation-sqlalchemy==0.66b2` via `uv add`)
- Test: `backend/tests/unit/test_logging.py`

**Interfaces:**
- Consumes: `mask` (Task 1).
- Produces:
  - `request_id_var: ContextVar[str | None]` (default `None`).
  - `class JsonFormatter(logging.Formatter)` — one JSON object per line with the Global Constraints fields; `trace_id`/`span_id` from `opentelemetry.trace.get_current_span()` (or `null` when the span context is not valid); extras = record attributes that are not standard `LogRecord` attributes.
  - `class MaskingFilter(logging.Filter)` — sets `record.msg = mask(record.getMessage())`, `record.args = None`, and masks every extra attribute with its own key. Returns `True`.
  - `setup_logging() -> None` — root logger level INFO, removes old root handlers, adds one `StreamHandler(sys.stdout)` with `JsonFormatter` + `MaskingFilter`. For loggers `uvicorn`, `uvicorn.error`, `uvicorn.access`, `saq`: clear their handlers, `propagate = True`. Safe to call twice (no duplicate handlers).

- [ ] **Step 1: Write the failing tests** (capture with a `StringIO` swapped onto the root handler's stream, or `capsys`; parse each line with `json.loads`)

```python
def test_log_line_is_json_with_ids():           # inside tracer.start_as_current_span and request_id_var.set("abc")
    line = ...; assert line["message"] == "hello" and line["request_id"] == "abc"
    assert line["trace_id"] == format(span.get_span_context().trace_id, "032x")
    assert line["span_id"] == format(span.get_span_context().span_id, "016x")
    assert set(line) >= {"timestamp", "level", "logger", "message", "request_id", "trace_id", "span_id"}

def test_log_line_outside_request_has_null_ids():
    assert line["request_id"] is None and line["trace_id"] is None

def test_child_logger_message_is_masked():      # logging.getLogger("app.x").info("call %s", "9876543210")
    assert line["message"] == "call [PHONE]"

def test_extra_address_field_is_masked():       # .info("saved", extra={"address": "12 MG Road"})
    assert line["address"] == "[MASKED]"

def test_uvicorn_loggers_use_root_json_handler():
    setup_logging(); setup_logging()
    assert len(logging.getLogger().handlers) == 1
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "saq"):
        assert logging.getLogger(name).handlers == [] and logging.getLogger(name).propagate
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest tests/unit/test_logging.py -v` → import error.
- [ ] **Step 3: `uv add` the four packages, then implement the logging part of `telemetry.py`.**
- [ ] **Step 4: Run, expect PASS**; also `uv run pytest tests/unit -q` stays green.
- [ ] **Step 5: Commit** — `feat: JSON logs with request and trace ids, masked`.

### Task 3: Traces for the API and Postgres, masked at export (CORE)

**Files:**
- Modify: `backend/app/core/telemetry.py` (tracing part), `backend/app/main.py`
- Modify: `backend/tests/integration/conftest.py` (session fixture `spans`)
- Test: `backend/tests/unit/test_span_masking.py`, `backend/tests/integration/test_tracing.py`

**Interfaces:**
- Consumes: `mask`, `setup_logging`, `request_id_var`.
- Produces:
  - `class MaskingSpanExporter(SpanExporter)` — `__init__(self, inner: SpanExporter)`; `export(spans)` passes `inner` new `ReadableSpan` copies whose attributes and each event's attributes are `mask(value, key)`; `shutdown`/`force_flush` delegate.
  - `add_span_exporter(exporter: SpanExporter) -> None` — adds `BatchSpanProcessor(MaskingSpanExporter(exporter))` to the global provider. The only way any exporter is attached.
  - `setup_telemetry(service_name: str) -> None` — once per process (module flag): `setup_logging()`; set a global `TracerProvider(resource=Resource.create({"service.name": service_name}))`; `SQLAlchemyInstrumentor().instrument()` (global patch, so the cached engine created later is traced); if `OTEL_EXPORTER_OTLP_ENDPOINT` is set: `add_span_exporter(OTLPSpanExporter())` and an OTel `LoggerProvider` + `LoggingHandler` on the root logger with the same `MaskingFilter`.
  - `flush_telemetry() -> None` — `force_flush()` on the tracer and logger providers.
  - `add_request_id(app: FastAPI) -> None` — HTTP middleware: `request_id_var.set(uuid4().hex)`, sets response header `X-Request-ID`, resets the var after.
  - `main.py`: `setup_telemetry("sevadesk-backend")` before `FastAPI(...)`; then `add_request_id(app)` and `FastAPIInstrumentor.instrument_app(app)`.
- Test fixture `spans` (session, in integration `conftest.py`): `add_span_exporter(InMemorySpanExporter())` once; yields a callable `finished() -> list[ReadableSpan]` that calls `flush_telemetry()` and returns spans; each test calls `.clear()` first.

- [ ] **Step 1: Write the failing tests**

```python
# unit/test_span_masking.py — a local TracerProvider + SimpleSpanProcessor(MaskingSpanExporter(memory))
def test_span_attributes_and_events_are_masked():
    with tracer.start_as_current_span("s") as s:
        s.set_attribute("note", "call 9876543210"); s.set_attribute("address", "12 MG Road")
        s.add_event("err", {"msg": "+91 98765 43210"})
    span = memory.get_finished_spans()[0]
    assert span.attributes["note"] == "call [PHONE]" and span.attributes["address"] == "[MASKED]"
    assert span.events[0].attributes["msg"] == "[PHONE]"

# integration/test_tracing.py
def test_hello_makes_one_trace_with_sql_span(client, spans):
    response = client.get("/api/v1/hello")
    server = [s for s in spans() if s.kind == SpanKind.SERVER][0]
    sql = [s for s in spans() if s.attributes.get("db.system") == "postgresql"]
    assert sql and all(s.context.trace_id == server.context.trace_id for s in sql)

def test_response_has_request_id_header(client):
    assert re.fullmatch(r"[0-9a-f]{32}", client.get("/api/v1/hello").headers["X-Request-ID"])

def test_incoming_traceparent_is_continued(client, spans):   # what Caddy sends
    tp = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    client.get("/api/v1/hello", headers={"traceparent": tp})
    assert any(format(s.context.trace_id, "032x") == "0af7651916cd43dd8448eb211c80319c" for s in spans())
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest tests/unit/test_span_masking.py tests/integration/test_tracing.py -v`.
- [ ] **Step 3: Implement the tracing part, the `main.py` wiring, and the `spans` fixture.**
- [ ] **Step 4: Run, expect PASS**; then the full suite `uv run pytest -q` stays green and coverage ≥ 80%.
- [ ] **Step 5: Commit** — `feat: trace API and Postgres, mask spans before export`.

**Checkpoint:** show the user one JSON log line and the span list from a test run.

### Task 4: The job carries `traceparent`; the worker joins the trace (CORE)

**Files:**
- Create: `backend/app/core/jobs.py`
- Modify: `backend/app/core/telemetry.py` (add `job_span`), `backend/app/core/hello_router.py`, `backend/app/worker.py`
- Modify: `backend/tests/integration/conftest.py` (clear `get_queue` cache in `client`)
- Test: `backend/tests/unit/test_jobs.py`, `backend/tests/integration/test_trace_job.py`

**Interfaces:**
- Consumes: `request_id_var`, `setup_telemetry`, `flush_telemetry`, `spans` fixture.
- Produces:
  - `jobs.py`: `TRACE_PING_JOB = "trace_ping"`; `job_context() -> dict[str, str | None]` — `{"traceparent": ..., "request_id": request_id_var.get()}`, `traceparent` via `opentelemetry.propagate.inject` into a dict; `get_queue() -> saq.Queue` (`lru_cache`, `Queue.from_url(get_settings().redis_url)`); `async def enqueue(job_name: str, **kwargs) -> None` — `await get_queue().enqueue(job_name, **kwargs)`; on any exception, `logger.exception("enqueue failed", extra={"job": job_name})` and return (no re-raise).
  - `telemetry.py`: `job_span(name: str, traceparent: str | None, request_id: str | None)` — context manager: extracts the parent context from `{"traceparent": traceparent}`, starts span `name` with kind `CONSUMER` under it, sets `request_id_var`, resets both on exit.
  - `hello_router.get_hello` gains `background_tasks: BackgroundTasks` and calls `background_tasks.add_task(enqueue, TRACE_PING_JOB, **job_context())`. `job_context()` runs in the handler (span still active); `enqueue` runs after the response.
  - `worker.py`: `async def trace_ping(ctx: dict, *, traceparent: str | None = None, request_id: str | None = None) -> None` — inside `job_span("trace_ping", traceparent, request_id)`, logs `"trace ping received"`; registered in `settings["functions"]`; `startup` calls `setup_telemetry("sevadesk-worker")` first; `shutdown` calls `flush_telemetry()`. The heartbeat cron is not traced.

- [ ] **Step 1: Write the failing tests**

```python
# unit/test_jobs.py
def test_job_context_carries_current_trace():          # inside a span, request_id_var set to "r1"
    ctx = job_context()
    assert ctx["traceparent"].split("-")[1] == format(span.get_span_context().trace_id, "032x")
    assert ctx["request_id"] == "r1"

def test_job_span_continues_parent_trace():            # local provider + memory exporter
    with job_span("trace_ping", tp, "r1"): assert request_id_var.get() == "r1"
    child = memory.get_finished_spans()[0]
    assert child.context.trace_id == parent_trace_id and child.parent.span_id == parent_span_id
    assert request_id_var.get() is None

def test_worker_registers_trace_ping():
    assert TRACE_PING_JOB in [f.__name__ for f in worker.settings["functions"]]

# integration/test_trace_job.py
def test_hello_enqueues_job_with_its_traceparent(client, spans, monkeypatch):  # fake queue records calls
    client.get("/api/v1/hello")
    name, kwargs = recorded[0]
    server = [s for s in spans() if s.kind == SpanKind.SERVER][0]
    assert name == "trace_ping" and kwargs["traceparent"].split("-")[1] == format(server.context.trace_id, "032x")

async def test_enqueued_job_round_trips_through_valkey(redis_url, monkeypatch):  # real SAQ queue
    await enqueue(TRACE_PING_JOB, traceparent=tp, request_id="r1")
    job = await get_queue().dequeue(timeout=2)
    assert job.function == "trace_ping" and job.kwargs == {"traceparent": tp, "request_id": "r1"}

def test_hello_still_ok_when_enqueue_fails(client, monkeypatch, caplog):  # REDIS_URL -> closed port
    assert client.get("/api/v1/hello").status_code == 200
    assert any(r.getMessage() == "enqueue failed" for r in caplog.records)
```

(Async tests: use `asyncio.run(...)` inside a sync test, so no new pytest plugin is needed.)

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest tests/unit/test_jobs.py tests/integration/test_trace_job.py -v`.
- [ ] **Step 3: Implement `jobs.py`, `job_span`, the router change, and the worker job.**
- [ ] **Step 4: Run, expect PASS**; full suite `uv run pytest -q` green, coverage ≥ 80%; `uv run lint-imports` passes (core still imports no entry point).
- [ ] **Step 5: Commit** — `feat: hello enqueues a traced job; worker joins the trace`.

**Checkpoint:** user predicts what the worker span's parent is, then we look at the test output.

### Task 5: Collector, Caddy span, local Grafana — live check (STANDARD/BOILERPLATE)

**Files:**
- Create: `infra/compose/otel-collector.yaml`
- Modify: `infra/compose/docker-compose.yml`, `infra/compose/Caddyfile`, `infra/compose/.env.example`, `README.md`
- Test: `backend/tests/unit/test_otel_only.py`

**Interfaces / values:**
- Collector (`otel/opentelemetry-collector-contrib:0.163.2`, service `otel-collector`, config mounted read-only): receivers `otlp` grpc `0.0.0.0:4317` + http `0.0.0.0:4318`; processor `batch`; exporter `otlphttp` with `endpoint: ${env:OTLP_EXPORT_ENDPOINT}` and header `Authorization: ${env:OTLP_EXPORT_AUTH}`; pipelines `traces` and `logs`.
- `lgtm` service: `grafana/otel-lgtm:0.39.0`, port `3001:3000` (Grafana UI at http://localhost:3001).
- Compose env: collector `OTLP_EXPORT_ENDPOINT: ${OTLP_EXPORT_ENDPOINT:-http://lgtm:4318}`, `OTLP_EXPORT_AUTH: ${OTLP_EXPORT_AUTH:-}`; backend and worker `OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-collector:4318`; caddy `OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-collector:4317`, `OTEL_SERVICE_NAME: sevadesk-caddy` (Caddy exports gRPC only — this is why the collector exists).
- Caddyfile: `tracing { span "{http.request.method} {http.request.uri.path}" }` inside the `:80` site, before the `handle` blocks.
- `.env.example`: commented `OTLP_EXPORT_ENDPOINT` / `OTLP_EXPORT_AUTH` with a one-line explanation each; values empty.

- [ ] **Step 1: Write the tests** in `test_otel_only.py`. Helper in the test file: `disallowed_imports(source: str) -> set[str]` — parses with `ast`, returns top-level imported packages that are not in `sys.stdlib_module_names`, not `app`, and not in the allow-list `{fastapi, pydantic, pydantic_settings, sqlalchemy, alembic, redis, saq, starlette, opentelemetry}`.
  - `test_detector_flags_a_vendor_sdk`: `disallowed_imports("import sentry_sdk\nfrom opentelemetry import trace") == {"sentry_sdk"}` (proves the check can fail).
  - `test_app_uses_only_opentelemetry_for_observability`: for every `backend/app/**/*.py`, `disallowed_imports(text) == set()` and `"grafana.net" not in text`.
  Run `uv run pytest tests/unit/test_otel_only.py -v` → both PASS (the guard locks in what Tasks 2–4 built).
- [ ] **Step 2: Add the collector config, compose services, Caddy tracing, `.env.example`.**
- [ ] **Step 3: Live check.** `docker compose -f infra/compose/docker-compose.yml up --build -d`; open http://localhost twice; `docker compose logs backend worker --tail 20` → every line is JSON with `request_id` and `trace_id`. In http://localhost:3001 → Explore → Tempo → search service `sevadesk-caddy`: one trace with spans from `sevadesk-caddy`, `sevadesk-backend` (handler + SQL), `sevadesk-worker` (`trace_ping`). Loki shows the logs with the same trace ID. Save a screenshot or the trace ID in the learning note.
- [ ] **Step 4: README** — "Observability" section: where to look (http://localhost:3001), and how to switch to Grafana Cloud with two env vars.
- [ ] **Step 5: Commit** — `feat: collector, Caddy span, and local Grafana for traces`.

### Task 6: Grafana Cloud by config only, notes, and finish

**Files:**
- Create: `docs/learning/1-5.md`
- Modify: `docs/learning/glossary.md`, `_bmad-output/implementation-artifacts/sprint-status.yaml`

- [ ] **Step 1: User creates a free Grafana Cloud stack** (I give the click steps): Connections → OpenTelemetry (OTLP) → copy the OTLP endpoint (`https://otlp-gateway-<region>.grafana.net/otlp`) and create a token. In `infra/compose/.env` only: `OTLP_EXPORT_ENDPOINT=<endpoint>`, `OTLP_EXPORT_AUTH=Basic <base64 of instanceId:token>`. No code change.
- [ ] **Step 2: Live check in Grafana Cloud.** `docker compose up -d otel-collector` (restart only the collector); load http://localhost; Explore → Tempo → find the trace with all four parts (FR-4 acceptance). Confirm `git status` shows no `.env`.
- [ ] **Step 3: Notes.** `docs/learning/1-5.md` (built, why, concept, key files, the two known limits); glossary terms: span, trace, traceparent, context propagation, OTLP, collector, exporter, PII masking.
- [ ] **Step 4: Final review** (Opus reviewer on the whole branch), fix findings with regression tests.
- [ ] **Step 5: Understanding Gate + hands-on task**, then mark `done` in `sprint-status.yaml` inside the PR, push, `gh pr create`, wait green, `gh pr merge --merge --delete-branch`, close #5.
