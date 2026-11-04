# Unit tests: every log line is one JSON object with request_id + trace_id, and is masked.
import io
import json
import logging
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.trace import TracerProvider

from app.core.telemetry import MaskingFilter, add_request_id, request_id_var, setup_logging

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
    for name in ("uvicorn", "uvicorn.error", "saq"):
        assert logging.getLogger(name).handlers == []
        assert logging.getLogger(name).propagate is True


def test_uvicorn_access_log_is_off(read_lines):
    # Our "request finished" line replaces uvicorn's access line.
    # (We do not assert hasHandlers(): pytest adds its own capture handlers to
    # non-propagating loggers, so it is always True inside a test.)
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.info('127.0.0.1:1 - "GET / HTTP/1.1" 200')
    assert access_logger.propagate is False
    assert [line for line in read_lines() if line["logger"] == "uvicorn.access"] == []


def test_exception_text_is_masked_in_json(read_lines):
    try:
        raise ValueError("bad phone 9876543210")
    except ValueError:
        logging.getLogger("app.x").exception("failed")
    line = read_lines()[-1]
    assert "bad phone [PHONE]" in line["exception"]
    assert "9876543210" not in json.dumps(line)


@pytest.fixture
def otlp_logs():
    # A logger whose lines go through MaskingFilter into an in-memory OTLP log exporter.
    exporter = InMemoryLogRecordExporter()
    provider = LoggerProvider()
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    handler = LoggingHandler(logger_provider=provider)
    handler.addFilter(MaskingFilter())
    otlp_logger = logging.getLogger("app.otlp_test")
    otlp_logger.addHandler(handler)
    otlp_logger.propagate = False
    otlp_logger.setLevel(logging.INFO)
    yield otlp_logger, exporter
    otlp_logger.removeHandler(handler)


def test_exception_text_is_masked_in_otlp_export(otlp_logs):
    otlp_logger, exporter = otlp_logs
    try:
        raise ValueError("bad phone 9876543210")
    except ValueError:
        otlp_logger.exception("failed")
    record = exporter.get_finished_logs()[0].log_record
    exported = f"{record.body} {dict(record.attributes)}"  # everything that is sent out
    assert "[PHONE]" in exported
    assert "9876543210" not in exported


def test_otlp_log_has_request_id(otlp_logs):
    otlp_logger, exporter = otlp_logs
    token = request_id_var.set("r1")
    try:
        otlp_logger.info("hello")
    finally:
        request_id_var.reset(token)
    assert exporter.get_finished_logs()[0].log_record.attributes["request_id"] == "r1"


def test_unhandled_error_logs_request_failed_with_id(read_lines):
    app = FastAPI()
    add_request_id(app)

    @app.get("/boom")
    def boom():
        raise RuntimeError("boom 9876543210")

    response = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert response.status_code == 500
    failed = [line for line in read_lines() if line["message"] == "request failed"]
    assert len(failed) == 1
    assert re.fullmatch(r"[0-9a-f]{32}", failed[0]["request_id"])
    assert failed[0]["path"] == "/boom"
    assert "boom [PHONE]" in failed[0]["exception"]
