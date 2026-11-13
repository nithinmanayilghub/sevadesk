# Unit tests for the error envelope: {"error": {"code", "message", "fields"?}}.
# Covers AppError, request validation errors (422), and unexpected errors (500).
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import AppError, FieldError, register_error_handlers


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


class NameBody(BaseModel):
    name: str


def make_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.post("/t")
    def take_name(body: NameBody):
        return {"ok": True}

    @app.get("/fields")
    def with_fields():
        raise AppError(
            code="email_taken", message="taken", status_code=409, fields=[FieldError(field="email", message="x")]
        )

    @app.get("/crash")
    def crash():
        raise RuntimeError("secret detail")

    return app


def test_validation_error_uses_envelope_with_fields():
    # Behaviour: a missing field comes back as a field error in our envelope, not FastAPI's format.
    response = TestClient(make_app()).post("/t", json={})
    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "Some fields need fixing.",
            "fields": [{"field": "name", "message": "This field is required."}],
        }
    }


def test_invalid_json_gives_envelope_without_fields():
    # Behaviour: broken JSON is a validation error with no field list (the key is left out).
    response = TestClient(make_app()).post("/t", content="{", headers={"content-type": "application/json"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert "fields" not in body["error"]


def test_app_error_with_fields():
    response = TestClient(make_app()).get("/fields")
    assert response.status_code == 409
    assert response.json()["error"]["fields"] == [{"field": "email", "message": "x"}]


def test_unexpected_error_gives_500_envelope():
    # Behaviour: a crash returns our envelope and never shows the internal error text.
    response = TestClient(make_app(), raise_server_exceptions=False).get("/crash")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret detail" not in response.text
