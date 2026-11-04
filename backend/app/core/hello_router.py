# The GET /api/v1/hello route: proves browser -> API -> Postgres -> worker works, in one trace.
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from app.core.app_meta import get_hello_value
from app.core.db import SessionDep
from app.core.jobs import TRACE_PING_JOB, enqueue, job_context
from app.core.settings import get_settings

router = APIRouter(prefix="/api/v1")


class HelloResponse(BaseModel):
    message: str
    version: str


@router.get("/hello", operation_id="get_hello")
def get_hello(session: SessionDep, background_tasks: BackgroundTasks) -> HelloResponse:
    message = get_hello_value(session)
    # job_context() runs now, while this request's span is active, so it captures our trace.
    # enqueue runs after the response is sent, so after the commit (AD-15).
    background_tasks.add_task(enqueue, TRACE_PING_JOB, **job_context())
    return HelloResponse(message=message, version=get_settings().app_version)
