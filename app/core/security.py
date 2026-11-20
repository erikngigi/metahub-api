"""Configure stdout logging format and level while quieting noisy HTTP libraries."""

import secrets

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.core.config import Settings, get_settings

_api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,  # we raise our own error for a consistent message
    description="API key issued to the desktop client",
)


async def require_api_key(
    api_key: str | None = Security(_api_key_header),
    settings: Settings = Depends(get_settings),
) -> None:
    """Dependency: rejects the request unless it carries a valid X-API-Key.
    Fails closed: if no keys are configured, every request is rejected."""
    valid_keys = settings.client_api_key_set

    if api_key and valid_keys:
        provided = api_key.encode()
        # Constant-time comparison; checks every key to avoid timing differences.
        matches = [secrets.compare_digest(provided, k.encode()) for k in valid_keys]
        if any(matches):
            return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API key",
        headers={"WWW-Authenticate": "ApiKey"},
    )
