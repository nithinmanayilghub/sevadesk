# Integration tests: /hello sends a job carrying its traceparent; the worker joins the same trace.
import asyncio
import logging

import redis
from opentelemetry import trace
from opentelemetry.trace import SpanKind

from app.core import jobs
from app.core.jobs import TRACE_PING_JOB, enqueue, get_queue, job_context
from app.core.settings import get_settings

TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"


class FakeQueue:
    """Records enqueue calls instead of talking to Valkey."""

    def __init__(self):
        self.calls = []

    async def enqueue(self, job_name, **kwargs):
        self.calls.append((job_name, kwargs))


def test_hello_enqueues_job_with_its_traceparent(client, spans, monkeypatch):
    fake = FakeQueue()
    monkeypatch.setattr(jobs, "get_queue", lambda: fake)
    spans.clear()
    response = client.get("/api/v1/hello")  # TestClient also runs the background task
    server = [s for s in spans.finished() if s.kind == SpanKind.SERVER][0]
    name, kwargs = fake.calls[0]
    assert name == "trace_ping"
    assert kwargs["traceparent"].split("-")[1] == format(server.context.trace_id, "032x")
    assert kwargs["request_id"] == response.headers["X-Request-ID"]


def test_enqueued_job_round_trips_through_valkey(redis_url, monkeypatch):
    # Earlier /hello tests left jobs in this shared Valkey; start from an empty queue.
    redis.Redis.from_url(redis_url).flushdb()
    monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://unused/unused")
    get_settings.cache_clear()
    get_queue.cache_clear()

    async def round_trip():
        await enqueue(TRACE_PING_JOB, traceparent=TRACEPARENT, request_id="r1")
        job = await get_queue().dequeue(timeout=2)
        await get_queue().disconnect()
        return job

    try:
        job = asyncio.run(round_trip())
    finally:
        get_queue.cache_clear()  # its connections belong to the loop that just closed
        get_settings.cache_clear()
    assert job.function == "trace_ping"
    assert job.kwargs == {"traceparent": TRACEPARENT, "request_id": "r1"}


def test_worker_job_continues_the_trace(spans, client):
    from app import worker  # imported here: worker.py needs the env vars the client fixture sets

    # The request side: make a span and capture its label, like /hello does.
    with trace.get_tracer("test").start_as_current_span("request") as parent:
        payload = job_context()
    # The worker side: a different program, so no current span; only the label links them.
    spans.clear()
    asyncio.run(worker.trace_ping({}, **payload))
    child = [s for s in spans.finished() if s.name == "trace_ping"][0]
    assert child.kind == SpanKind.CONSUMER
    assert child.context.trace_id == parent.get_span_context().trace_id
    assert child.parent.span_id == parent.get_span_context().span_id


def test_hello_still_ok_when_enqueue_fails(client, monkeypatch, caplog):
    # Point the queue at a closed port: Valkey is "down".
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    get_settings.cache_clear()
    get_queue.cache_clear()
    with caplog.at_level(logging.ERROR):
        response = client.get("/api/v1/hello")
    get_queue.cache_clear()
    assert response.status_code == 200
    assert any(r.getMessage() == "enqueue failed" for r in caplog.records)
