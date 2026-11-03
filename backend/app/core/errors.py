# The error envelope for errors we raise on purpose (AppError): {"error": {"code", "message"}}.
# FastAPI's own 404/422/500 errors are not mapped yet.
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Raise this anywhere in a route to send a clean error to the client."""

    def __init__(self, code: str, message: str, status_code: int):
        super().__init__(message)
        self.code = code  # short machine-readable name, e.g. "dependency_unavailable"
        self.message = message  # human-readable sentence
        self.status_code = status_code  # HTTP status, e.g. 503


def register_error_handlers(app: FastAPI) -> None:
    # Turn an AppError into the envelope JSON with the error's own status code.
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    app.add_exception_handler(AppError, handle_app_error)
