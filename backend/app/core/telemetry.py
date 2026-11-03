# Telemetry: JSON logs with request + trace IDs. Everything passes through core.masking.mask (AD-13).
# Only OpenTelemetry APIs are used, so the backend tool can change by config alone.
import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

from opentelemetry import trace

from app.core.masking import mask

# The current request's ID. A ContextVar is like a global, but each request
# (and each async task) sees its own value. None = not inside a request or job.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Names every LogRecord has. Anything else on a record is an "extra" the caller added.
_STANDARD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
}

# Loggers owned by libraries. We remove their own handlers so their lines reach our JSON handler.
_LIBRARY_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "saq")


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
