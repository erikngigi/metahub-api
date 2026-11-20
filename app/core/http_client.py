"""Async HTTP wrapper with retries and standardized provider error mapping."""

import asyncio
import logging
from typing import Any

import httpx

from app.core.config import Settings
from app.exceptions.errors import (
    ProviderAuthError,
    ProviderBadResponse,
    ProviderNotFound,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)

logger = logging.getLogger(__name__)


class HttpClient:
    """Shared async client. Retries transient failures and translates every
    failure into one of our ProviderError types."""

    def __init__(self, settings: Settings) -> None:
        self._max_retries = settings.http_max_retries
        self._backoff = settings.http_retry_backoff_seconds
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                settings.http_timeout_seconds,
                connect=settings.http_connect_timeout_seconds,
            ),
            headers={"User-Agent": f"{settings.app_name}/1.0"},
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            follow_redirects=True,
        )

    async def get_json(
        self,
        provider: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Send an HTTP GET request and parse the response body as JSON.

        Retries transient network errors, timeouts, and ``5xx`` responses with
        exponential backoff, and maps HTTP and JSON errors to provider exceptions.

        Raises:
            ProviderAuthError: Upstream rejected credentials with ``401`` or ``403``.
            ProviderNotFound: Upstream returned ``404``.
            ProviderRateLimited: Upstream returned ``429``.
            ProviderBadResponse: Upstream returned another ``4xx`` status or invalid JSON.
            ProviderTimeout: Request timed out across all retry attempts.
            ProviderUnavailable: Network error or ``5xx`` status persisted after retries.
        """
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            if attempt:
                await asyncio.sleep(self._backoff * 2 ** (attempt - 1))
                logger.warning("Retrying %s (attempt %d)", provider, attempt + 1)

            try:
                response = await self._client.get(url, params=params, headers=headers)
            except httpx.TimeoutException:
                last_error = ProviderTimeout(provider, "request timed out")
                continue
            except httpx.HTTPError as exc:
                # Log only the exception type: its text can contain the URL (and API key).
                last_error = ProviderUnavailable(provider, f"network error: {type(exc).__name__}")
                continue

            status = response.status_code
            if status >= 500:
                last_error = ProviderUnavailable(provider, f"upstream returned {status}")
                continue
            if status in (401, 403):
                raise ProviderAuthError(provider, "upstream rejected credentials")
            if status == 404:
                raise ProviderNotFound(provider)
            if status == 429:
                raise ProviderRateLimited(provider)
            if status >= 400:
                raise ProviderBadResponse(provider, f"unexpected status {status}")

            try:
                return response.json()
            except ValueError as exc:
                raise ProviderBadResponse(provider, "response was not valid JSON") from exc

        assert last_error is not None
        raise last_error

    async def aclose(self) -> None:
        """Close the underlying ``httpx.AsyncClient`` connection pool."""
        await self._client.aclose()
