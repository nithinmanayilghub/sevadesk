# The FastAPI app: the entry point that uvicorn runs.
from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app.core import health_router, hello_router
from app.core.errors import register_error_handlers
from app.core.origin_guard import add_origin_guard
from app.core.telemetry import add_request_id, setup_telemetry
from app.modules.accounts import router as accounts_router
from app.modules.business import router as business_router

# First, so every log line and query after this is traced.
setup_telemetry("sevadesk-backend")

app = FastAPI(
    title="SevaDesk API",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
app.include_router(hello_router.router)
app.include_router(health_router.router)
app.include_router(accounts_router.router)
app.include_router(business_router.router)
register_error_handlers(app)
# Added before add_request_id, so it runs INSIDE it: a refused request still gets a request ID and a log line.
add_origin_guard(app)
add_request_id(app)
# Makes one server span per request, and joins an incoming traceparent (from Caddy).
FastAPIInstrumentor.instrument_app(app)
