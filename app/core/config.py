from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    app_name: str = "Metahub-API"
    environment: Literal["development", "staging", "production"] = "development"

    # --- Logging ---
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_json: bool = False

    # --- Client authentication (comma-separated list in .env) ---
    client_api_keys: str = ""

    # --- Outbound HTTP ---
    http_timeout_seconds: float = Field(10.0, gt=0)
    http_connect_timeout_seconds: float = Field(5.0, gt=0)
    http_max_retries: int = Field(2, ge=0, le=5)
    http_retry_backoff_seconds: float = Field(0.5, ge=0)

    # --- Providers ---
    tmdb_api_key: SecretStr | None = None
    tmdb_base_url: str = "https://api.themoviedb.org/3"

    @property
    def client_api_key_set(self) -> frozenset[str]:
        return frozenset(k.strip() for k in self.client_api_key_set.split(",") if k.strip())


@lru_cache
def get_settings() -> Settings:
    """Cached so .env is parsed once. Also usable as a FastAPI dependency"""
    return Settings()
