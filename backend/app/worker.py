# The SAQ background worker: a heartbeat every 10 s, plus the trace_ping job. Run: saq app.worker.settings
import logging
from datetime import UTC, datetime

import redis.asyncio
from saq import CronJob, Queue

from app.core.health import HEARTBEAT_KEY, HEARTBEAT_TTL_SECONDS
from app.core.settings import get_settings
from app.core.telemetry import flush_telemetry, job_span, setup_telemetry

logger = logging.getLogger(__name__)


async def write_heartbeat(ctx: dict) -> None:
    # Store the current time; the key expires on its own if the worker stops.
    # Not traced: a span every 10 s would only be noise.
    await ctx["redis"].set(HEARTBEAT_KEY, datetime.now(UTC).isoformat(), ex=HEARTBEAT_TTL_SECONDS)


async def trace_ping(ctx: dict, *, traceparent: str | None = None, request_id: str | None = None) -> None:
    # The name must match core.jobs.TRACE_PING_JOB. The span joins the request's trace.
    with job_span("trace_ping", traceparent, request_id):
        logger.info("trace ping received")


async def startup(ctx: dict) -> None:
    setup_telemetry("sevadesk-worker")  # first, so every log line after this is JSON
    ctx["redis"] = redis.asyncio.Redis.from_url(get_settings().redis_url)


async def shutdown(ctx: dict) -> None:
    await ctx["redis"].aclose()
    flush_telemetry()  # send spans still waiting in memory before the worker exits


# SAQ reads this dict. The cron's 6th field is seconds: "*/10" = every 10 s.
settings = {
    "queue": Queue.from_url(get_settings().redis_url),
    "functions": [trace_ping],
    "cron_jobs": [CronJob(write_heartbeat, cron="* * * * * */10")],
    "startup": startup,
    "shutdown": shutdown,
}
