import pytest
from pydantic import ValidationError
from app.core.settings import Settings

def test_settings_read_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h:5432/d")
    monkeypatch.setenv("APP_VERSION", "1.2.3")
    s = Settings()
    assert s.database_url == "postgresql+psycopg://u:p@h:5432/d"
    assert s.app_version == "1.2.3"

def test_settings_default_version(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h:5432/d")
    monkeypatch.delenv("APP_VERSION", raising=False)
    assert Settings().app_version == "dev"

def test_settings_require_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings()
