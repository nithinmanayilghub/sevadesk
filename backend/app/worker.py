# The SAQ background worker: writes a heartbeat to Valkey every 10 s. Run: saq app.worker.settings
from datetime import UTC, datetime

import redis.asyncio
from saq import CronJob, Queue

from app.core.health import HEARTBEAT_KEY, HEARTBEAT_TTL_SECONDS
from app.core.settings import get_settings


async def write_heartbeat(ctx: dict) -> None:
    # Store the current time; the key expires on its own if the worker stops.
    await ctx["redis"].set(
        HEARTBEAT_KEY, datetime.now(UTC).isoformat(), ex=HEARTBEAT_TTL_SECONDS
    )


async def startup(ctx: dict) -> None:
    ctx["redis"] = redis.asyncio.Redis.from_url(get_settings().redis_url)


async def shutdown(ctx: dict) -> None:
    await ctx["redis"].aclose()


# SAQ reads this dict. The cron's 6th field is seconds: "*/10" = every 10 s.
settings = {
    "queue": Queue.from_url(get_settings().redis_url),
    "functions": [],
    "cron_jobs": [CronJob(write_heartbeat, cron="* * * * * */10")],
    "startup": startup,
    "shutdown": shutdown,
}
