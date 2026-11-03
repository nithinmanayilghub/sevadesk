# Unit tests: every log line is one JSON object with request_id + trace_id, and is masked.
import io
import json
import logging

import pytest
from opentelemetry.sdk.trace import TracerProvider

from app.core.telemetry import request_id_var, setup_logging

# A local tracer: enough to make a "current span" without touching global setup.
tracer = TracerProvider().get_tracer("test")


@pytest.fixture
def read_lines():
    # Save the root logger, install our JSON logging, then put everything back after the test.
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    setup_logging()
    # Point our stdout handler at an in-memory buffer, so the test can read what it wrote.
    buffer = io.StringIO()
    root.handlers[0].setStream(buffer)

    def lines() -> list[dict]:
        return [json.loads(line) for line in buffer.getvalue().splitlines() if line.strip()]

    yield lines
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)


def test_log_line_is_json_with_ids(read_lines):
    token = request_id_var.set("abc")
    try:
        with tracer.start_as_current_span("work") as span:
            logging.getLogger("app.test").info("hello")
    finally:
        request_id_var.reset(token)
    line = read_lines()[-1]
    ctx = span.get_span_context()
    assert line["message"] == "hello"
    assert line["request_id"] == "abc"
    assert line["trace_id"] == format(ctx.trace_id, "032x")
    assert line["span_id"] == format(ctx.span_id, "016x")
    assert line["level"] == "INFO"
    assert line["logger"] == "app.test"
    assert set(line) >= {"timestamp", "level", "logger", "message", "request_id", "trace_id", "span_id"}


def test_log_line_outside_request_has_null_ids(read_lines):
    logging.getLogger("app.test").info("idle")
    line = read_lines()[-1]
    assert line["request_id"] is None
    assert line["trace_id"] is None
    assert line["span_id"] is None


def test_child_logger_message_is_masked(read_lines):
    logging.getLogger("app.x").info("call %s", "9876543210")
    assert read_lines()[-1]["message"] == "call [PHONE]"


def test_extra_address_field_is_masked(read_lines):
    logging.getLogger("app.x").info("saved", extra={"address": "12 MG Road", "seats": 2})
    line = read_lines()[-1]
    assert line["address"] == "[MASKED]"
    assert line["seats"] == 2


def test_uvicorn_loggers_use_root_json_handler(read_lines):
    setup_logging()  # second call: must not add a second handler
    assert len(logging.getLogger().handlers) == 1
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "saq"):
        assert logging.getLogger(name).handlers == []
        assert logging.getLogger(name).propagate is True
