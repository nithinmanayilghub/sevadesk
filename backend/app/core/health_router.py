# The GET /api/health route: tells a load balancer or a person if the app can reach its dependencies.
import redis
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.errors import AppError
from app.core.health import check_database, check_redis, check_worker_heartbeat

router = APIRouter(prefix="/api/health")


class HealthResponse(BaseModel):
    status: str
    database: str
    redis: str


@router.get("", operation_id="get_health")
def get_health() -> HealthResponse:
    # Order matters: the error message lists failures in this order.
    checks = {"database": check_database(), "redis": check_redis()}
    failing = [name for name, ok in checks.items() if not ok]
    if failing:
        raise AppError(
            code="dependency_unavailable",
            message="Not reachable: " + ", ".join(failing),
            status_code=503,
        )
    return HealthResponse(status="ok", database="ok", redis="ok")


class WorkerHealthResponse(BaseModel):
    status: str


@router.get("/worker", operation_id="get_worker_health")
def get_worker_health() -> WorkerHealthResponse:
    try:
        alive = check_worker_heartbeat()
    except redis.RedisError:
        raise AppError(
            code="dependency_unavailable",
            message="Not reachable: redis",
            status_code=503,
        )
    if not alive:
        raise AppError(
            code="worker_unavailable",
            message="No worker heartbeat in the last 30 seconds",
            status_code=503,
        )
    return WorkerHealthResponse(status="ok")
