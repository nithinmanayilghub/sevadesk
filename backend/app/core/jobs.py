# Jobs: names, and the one helper that sends a job to the worker queue (AD-7, AD-15).
# Every job carries "traceparent" and "request_id", so the worker joins the same trace.
import logging
from functools import lru_cache

from opentelemetry import propagate
from saq import Queue

from app.core.settings import get_settings
from app.core.telemetry import request_id_var

logger = logging.getLogger(__name__)

# A test job: proves a request and a worker job show up in one trace (Story 1.5).
TRACE_PING_JOB = "trace_ping"


def job_context() -> dict[str, str | None]:
    """Capture the current trace and request ID. Call it INSIDE the request, while its span is active."""
    carrier: dict[str, str] = {}
    # inject() writes the current span as a W3C "traceparent" text label into the dict.
    propagate.inject(carrier)
    return {"traceparent": carrier.get("traceparent"), "request_id": request_id_var.get()}


@lru_cache
def get_queue() -> Queue:
    # Cached: one queue client for the whole app. Tests call get_queue.cache_clear().
    return Queue.from_url(get_settings().redis_url)


async def enqueue(job_name: str, **kwargs) -> None:
    """Send a job to the worker. Run it AFTER the commit (e.g. as a FastAPI background task)."""
    try:
        await get_queue().enqueue(job_name, **kwargs)
    except Exception:
        # The response is already sent, so we cannot report this to the client. Log it instead.
        logger.exception("enqueue failed", extra={"job": job_name})
