# The FastAPI app: the entry point that uvicorn runs.
from fastapi import FastAPI

from app.core import hello_router

app = FastAPI(
    title="SevaDesk API",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
app.include_router(hello_router.router)
