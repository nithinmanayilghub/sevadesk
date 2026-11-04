# Unit tests: a job captures the current trace (traceparent) and request ID; the worker knows the job.
from opentelemetry.sdk.trace import TracerProvider

from app.core.jobs import TRACE_PING_JOB, job_context
from app.core.settings import get_settings
from app.core.telemetry import request_id_var

tracer = TracerProvider().get_tracer("test")


def test_job_context_carries_current_trace():
    token = request_id_var.set("r1")
    try:
        with tracer.start_as_current_span("request") as span:
            context = job_context()
    finally:
        request_id_var.reset(token)
    # traceparent = "00-<32 hex trace id>-<16 hex span id>-01"
    version, trace_hex, span_hex, flags = context["traceparent"].split("-")
    assert trace_hex == format(span.get_span_context().trace_id, "032x")
    assert span_hex == format(span.get_span_context().span_id, "016x")
    assert context["request_id"] == "r1"


def test_worker_registers_trace_ping(monkeypatch):
    # worker.py builds its queue on import, so it needs these env vars (no connection is made).
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://unused/unused")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    get_settings.cache_clear()
    from app import worker

    assert TRACE_PING_JOB == "trace_ping"
    assert TRACE_PING_JOB in [f.__name__ for f in worker.settings["functions"]]
