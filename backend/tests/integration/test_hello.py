# Integration tests: the hello endpoint reads from a real, migrated Postgres.
from sqlalchemy import inspect

from app.core.db import get_engine


def test_hello_reads_value_from_database(client):
    response = client.get("/api/v1/hello")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello from SevaDesk", "version": "test-1"}


def test_migration_creates_only_app_meta(client):
    tables = set(inspect(get_engine()).get_table_names())
    assert tables == {"alembic_version", "app_meta"}


def test_openapi_schema_lists_hello(client):
    schema = client.get("/api/openapi.json").json()
    assert "/api/v1/hello" in schema["paths"]
