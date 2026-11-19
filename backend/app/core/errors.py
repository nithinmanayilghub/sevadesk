# The one error envelope (AR-3): {"error": {"code", "message", "fields"?}}.
# - AppError: errors we raise on purpose, with their own status code.
# - RequestValidationError: bad input (422). Each bad body field is listed in "fields".
# - Any other exception: 500 with a safe message. The real error goes only to the logs.
# "fields" is left out when there are no field errors.

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class FieldError(BaseModel):
    field: str  # the request field name, e.g. "email"
    message: str  # a sentence to show next to that field


class ErrorBody(BaseModel):
    code: str
    message: str
    fields: list[FieldError] | None = None


class ErrorEnvelope(BaseModel):
    """The error response shape, for the OpenAPI schema (so the frontend types know it)."""

    error: ErrorBody


class AppError(Exception):
    """Raise this anywhere in a route to send a clean error to the client."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        fields: list[FieldError] | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(message)
        self.code = code  # short machine-readable name, e.g. "dependency_unavailable"
        self.message = message  # human-readable sentence
        self.status_code = status_code  # HTTP status, e.g. 503
        self.fields = fields  # optional per-field errors
        self.headers = headers  # optional response headers, e.g. {"Retry-After": "900"}


class NotFound(AppError):
    """404: the record does not exist, OR it belongs to another Business (FR-11).

    Both cases get the same answer on purpose, so a caller cannot learn that
    another Business's record exists.
    """

    def __init__(self):
        super().__init__(code="not_found", message="We could not find that.", status_code=404)


class Forbidden(AppError):
    """403: we know who you are, but your Role may not do this (FR-10).

    Services raise it BEFORE they look up any record, so a 403 never tells a
    caller whether a record exists. Raising it also rolls back the request's
    transaction (core/db.py), so a forbidden request changes nothing.
    """

    def __init__(self):
        super().__init__(code="forbidden", message="You don't have access to this.", status_code=403)


def error_response(status_code: int, code: str, message: str, fields: list[FieldError] | None = None) -> JSONResponse:
    """Build the one error envelope. Public, so middleware (which runs outside the handlers) uses it too."""
    body = ErrorBody(code=code, message=message, fields=fields or None)
    # exclude_none leaves "fields" out when there are none.
    return JSONResponse(status_code=status_code, content={"error": body.model_dump(exclude_none=True)})


def _field_errors(exc: RequestValidationError) -> list[FieldError]:
    fields = []
    for error in exc.errors():
        loc = error.get("loc", ())
        # Only body fields: loc looks like ("body", "email"). Broken JSON gives
        # ("body", <character position>), which is not a field, so it needs a str check.
        # A nested field is named by its dotted path: ("body", "monday", "end_time") ->
        # "monday.end_time". List positions stay as numbers: ("body", "roles", 0) -> "roles.0".
        if len(loc) >= 2 and loc[0] == "body" and isinstance(loc[1], str):
            message = "This field is required." if error["type"] == "missing" else error["msg"]
            fields.append(FieldError(field=".".join(map(str, loc[1:])), message=message))
    return fields


def register_error_handlers(app: FastAPI) -> None:
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        response = error_response(exc.status_code, exc.code, exc.message, exc.fields)
        response.headers.update(exc.headers or {})
        return response

    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(422, "validation_error", "Some fields need fixing.", _field_errors(exc))

    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # The request middleware also logs the error; the client never sees its text.
        return error_response(500, "internal_error", "Something went wrong. Please try again.")

    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
