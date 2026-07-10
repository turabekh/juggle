"""Application configuration, loaded from the environment.

Runtime *product* configuration (platform fee %, seat-hold TTL, etc.) lives in
the database and is edited through the admin panel (PRD §10.1). This file holds
only *deployment* configuration — connection strings, secrets, toggles that must
exist before the app can boot.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JUGGLE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = Field(default="local")
    debug: bool = Field(default=True)

    # Postgres / PostGIS
    database_url: str = Field(
        default="postgresql+psycopg://juggle:juggle@localhost:5433/juggle",
        description="SQLAlchemy URL. Uses psycopg3 driver + PostGIS-enabled Postgres.",
    )

    # Auth (JWT) — real values injected via env in every non-local environment.
    jwt_secret: str = Field(default="dev-insecure-change-me")
    jwt_algorithm: str = Field(default="HS256")
    access_token_ttl_minutes: int = Field(default=30)

    # CORS origins for the Quasar PWA during development.
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:9000"])


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so settings are parsed once per process."""
    return Settings()
