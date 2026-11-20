import os
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Must be a real OS variable: it decides which file to read.
_ACTIVE_ENV = os.getenv("ENVIRONMENT", "development").strip().lower()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", f".env.{_ACTIVE_ENV}"),  # later file wins
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    app_name: str = "Metahub-API"
    environment: Literal["development", "staging", "production"] = "development"

    # --- Logging ---
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_json: bool = False

    # --- Client authentication (comma-separated list) ---
    client_api_keys: str = ""

    # --- Outbound HTTP ---
    http_timeout_seconds: float = Field(10.0, gt=0)
    http_connect_timeout_seconds: float = Field(5.0, gt=0)
    http_max_retries: int = Field(2, ge=0, le=5)
    http_retry_backoff_seconds: float = Field(0.5, ge=0)

    # --- Providers Access Tokens ---
    tmdb_read_access_token: SecretStr | None = None

    # --- Providers URLs ---
    tmdb_base_url: str | None = None
    tvmaze_base_url: str | None = None
    tenrai_base_url: str | None = None

    @property
    def client_api_key_set(self) -> frozenset[str]:
        return frozenset(k.strip() for k in self.client_api_keys.split(",") if k.strip())

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached so env files are parsed once. Also usable as a FastAPI dependency."""
    return Settings()
