# Settings: reads the app's configuration from environment variables.
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Env vars are matched by field name, ignoring case: DATABASE_URL, APP_VERSION.
    # No .env file is read: docker compose passes the env vars in.
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str  # required: app will not start without it
    app_version: str = "dev"


@lru_cache
def get_settings() -> Settings:
    # Cached so we build Settings once. Tests call get_settings.cache_clear().
    return Settings()
