"""Application configuration — all settings from environment variables."""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    reload: bool = False

    # Database — path to ROT's SQLite DB, or connection string for Postgres
    database_url: str = "sqlite+aiosqlite:///./rot_signals.db"

    # Auth
    secret_key: str = Field(default="change-me-in-production-use-openssl-rand-hex-32")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # Tiers
    free_delay_seconds: int = 900   # 15 minutes
    free_page_limit: int = 10
    pro_page_limit: int = 200
    enterprise_page_limit: int = 1000

    # Rate limits (requests per minute)
    free_rpm: int = 20
    pro_rpm: int = 300
    enterprise_rpm: int = 5000

    # WebSocket
    ws_ping_interval: int = 30   # seconds
    ws_max_connections_free: int = 1
    ws_max_connections_pro: int = 5

    # CORS
    cors_origins: list[str] = ["*"]

    @field_validator("secret_key")
    @classmethod
    def warn_default_key(cls, v: str) -> str:
        if v == "change-me-in-production-use-openssl-rand-hex-32":
            import warnings
            warnings.warn("SECRET_KEY is using default value — set it in .env for production", stacklevel=2)
        return v


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
