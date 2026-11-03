# Unit test for the error envelope of AppError: {"error": {"code", "message"}}.
# FastAPI's own 404/422/500 errors are not mapped yet.
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import AppError, register_error_handlers


def test_app_error_becomes_envelope():
    # An AppError raised inside a route must turn into {"error": {...}} with its status code.
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom")
    def boom():
        raise AppError(code="dependency_unavailable", message="database is not reachable", status_code=503)

    response = TestClient(app).get("/boom")
    assert response.status_code == 503
    assert response.json() == {"error": {"code": "dependency_unavailable", "message": "database is not reachable"}}
