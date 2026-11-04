# Telemetry: JSON logs + traces with request and trace IDs. Everything passes through
# core.masking.mask (AD-13). Only OpenTelemetry APIs are used, so the place we send data
# to (local Grafana, Grafana Cloud, another tool) changes by env vars alone.
import json
import logging
import os
import sys
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI, Request
from opentelemetry import propagate, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult

from app.core.masking import mask

logger = logging.getLogger(__name__)

# The current request's ID. A ContextVar is like a global, but each request
# (and each async task) sees its own value. None = not inside a request or job.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Names every LogRecord has. Anything else on a record is an "extra" the caller added.
_STANDARD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
}

# Loggers owned by libraries. We remove their own handlers so their lines reach our JSON handler.
_LIBRARY_LOGGERS = ("uvicorn", "uvicorn.error", "saq")


def _extras(record: logging.LogRecord) -> dict:
    return {k: v for k, v in record.__dict__.items() if k not in _STANDARD_ATTRS}


class MaskingFilter(logging.Filter):
    """Masks the message and every extra field before any handler writes or exports it."""

    def filter(self, record: logging.LogRecord) -> bool:
        # getMessage() joins msg and args ("call %s" + "987...") so the masker sees the full text.
        record.msg = mask(record.getMessage())
        record.args = None
        for key, value in _extras(record).items():
            setattr(record, key, mask(value, key=key))
        return True  # never drop a line; only change it


class JsonFormatter(logging.Formatter):
    """Writes one JSON object per line, with request_id, trace_id, and span_id."""

    def format(self, record: logging.LogRecord) -> str:
        span_context = trace.get_current_span().get_span_context()
        has_span = span_context.is_valid
        line = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
            # Same hex format Grafana shows: 32 chars for trace, 16 for span.
            "trace_id": format(span_context.trace_id, "032x") if has_span else None,
            "span_id": format(span_context.span_id, "016x") if has_span else None,
            **_extras(record),
        }
        if record.exc_info:
            # A stack trace can hold data too, so it is masked as well.
            line["exception"] = mask(self.formatException(record.exc_info))
        return json.dumps(line, default=str, ensure_ascii=False)


def setup_logging() -> None:
    """Send all logs (ours and libraries') to stdout as masked JSON. Safe to call twice."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    # The filter sits on the handler, not on a logger: logger filters do not run
    # for lines that come up from child loggers such as "app.core.x".
    handler.addFilter(MaskingFilter())

    root = logging.getLogger()
    root.handlers[:] = [handler]  # replace, so a second call does not add a duplicate
    root.setLevel(logging.INFO)

    for name in _LIBRARY_LOGGERS:
        library_logger = logging.getLogger(name)
        library_logger.handlers.clear()
        library_logger.propagate = True

    # Uvicorn's access line is off: our "request finished" line (with request_id) replaces it.
    # Uvicorn writes access lines only if this logger has a handler somewhere, so we cut it off.
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = False


# ---------------------------------------------------------------- traces


def _masked_attributes(attributes) -> dict:
    return {key: mask(value, key=key) for key, value in (attributes or {}).items()}


class MaskingSpanExporter(SpanExporter):
    """A guard at the exit door: masks each span's attributes, then hands it to the real exporter."""

    def __init__(self, inner: SpanExporter):
        self.inner = inner

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        # Finished spans are read-only, so we build masked copies instead of changing them.
        masked = [
            ReadableSpan(
                name=span.name,
                context=span.context,
                parent=span.parent,
                resource=span.resource,
                attributes=_masked_attributes(span.attributes),
                events=[
                    Event(event.name, _masked_attributes(event.attributes), event.timestamp) for event in span.events
                ],
                links=span.links,
                kind=span.kind,
                status=span.status,
                start_time=span.start_time,
                end_time=span.end_time,
                instrumentation_scope=span.instrumentation_scope,
            )
            for span in spans
        ]
        return self.inner.export(masked)

    def shutdown(self) -> None:
        self.inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self.inner.force_flush(timeout_millis)


def add_span_exporter(exporter: SpanExporter) -> None:
    """The ONLY way to attach an exporter, so every exported span is masked first."""
    trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(MaskingSpanExporter(exporter)))


_logger_provider: LoggerProvider | None = None
_configured = False


def setup_telemetry(service_name: str) -> None:
    """Set up logs and traces for one program (API or worker). Runs once per process."""
    global _configured, _logger_provider
    if _configured:
        return
    _configured = True

    setup_logging()
    # service.name tells Grafana which program a span came from.
    resource = Resource.create({"service.name": service_name})
    trace.set_tracer_provider(TracerProvider(resource=resource))
    # Patch the Postgres driver (psycopg), so every query makes a span. We trace the driver,
    # not SQLAlchemy: the SQLAlchemy instrumentor does not support SQLAlchemy 2.1 yet.
    PsycopgInstrumentor().instrument()

    # No endpoint = send nothing (tests, CI). The OTLP exporters read this env var themselves.
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return
    add_span_exporter(OTLPSpanExporter())
    # Also send log lines over OTLP, with the same masking filter as stdout.
    _logger_provider = LoggerProvider(resource=resource)
    _logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    set_logger_provider(_logger_provider)
    otel_handler = LoggingHandler(logger_provider=_logger_provider)
    otel_handler.addFilter(MaskingFilter())
    logging.getLogger().addHandler(otel_handler)


def flush_telemetry() -> None:
    """Send any spans and log lines still waiting in memory (call before the program exits)."""
    provider = trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        provider.force_flush()
    if _logger_provider is not None:
        _logger_provider.force_flush()


def add_request_id(app: FastAPI) -> None:
    """Give every request a fresh ID, put it in the X-Request-ID header, and log one line."""

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        # We always make our own ID; a client-sent one could be fake or contain anything.
        token = request_id_var.set(uuid4().hex)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id_var.get()
            # Written inside the request span, so this line has both IDs.
            logger.info(
                "request finished",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            return response
        finally:
            request_id_var.reset(token)


@contextmanager
def job_span(name: str, traceparent: str | None, request_id: str | None) -> Iterator[None]:
    """Run a worker job inside a span that continues the trace named by traceparent."""
    # extract() reads the text label back into a "parent" context. No label = a new trace.
    parent = propagate.extract({"traceparent": traceparent} if traceparent else {})
    token = request_id_var.set(request_id)
    try:
        tracer = trace.get_tracer(__name__)
        # CONSUMER = this span handles a message that someone else sent.
        with tracer.start_as_current_span(name, context=parent, kind=trace.SpanKind.CONSUMER):
            yield
    finally:
        request_id_var.reset(token)
