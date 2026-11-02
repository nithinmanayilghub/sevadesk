# The GET /api/v1/hello route: proves browser -> API -> Postgres works.
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.app_meta import get_hello_value
from app.core.db import SessionDep
from app.core.settings import get_settings

router = APIRouter(prefix="/api/v1")


class HelloResponse(BaseModel):
    message: str
    version: str


@router.get("/hello", operation_id="get_hello")
def get_hello(session: SessionDep) -> HelloResponse:
    return HelloResponse(
        message=get_hello_value(session),
        version=get_settings().app_version,
    )
