# The FastAPI app: the entry point that uvicorn runs.
from fastapi import FastAPI

from app.core import health_router, hello_router
from app.core.errors import register_error_handlers

app = FastAPI(
    title="SevaDesk API",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
app.include_router(hello_router.router)
app.include_router(health_router.router)
register_error_handlers(app)
