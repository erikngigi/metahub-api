"""TMDB adapter: calls the TMDB v3 API and returns domain models.

This is the only module that knows TMDB's URLs and parameters. It fetches JSON,
validates it into ``models/raw/tmdb`` shapes, and hands them to ``tmdb_mapper``.

Pipeline position:
    controller -> TmdbProvider (this file) -> HttpClient -> TMDB
                                           -> tmdb_mapper -> domain models

Errors:
    Everything raised is a ``ProviderError`` subclass. TMDB reports problems
    with real HTTP status codes, which ``HttpClient`` already translates, so no
    error-text parsing is needed here.
"""

import asyncio
import logging
from typing import Any, TypeVar

from pydantic import BaseModel, SecretStr, ValidationError

from app.core.config import Settings
from app.core.http_client import HttpClient
from app.exceptions.errors import ProviderAuthError, ProviderBadResponse, ProviderNotFound
from app.mappers import tmdb_mapper
from app.models.domain.media import Media, MediaType
from app.models.domain.search_result import SearchResult
from app.models.raw.tmdb import (
    TmdbEpisode,
    TmdbExternalIds,
    TmdbMovieDetails,
    TmdbSearchResponse,
    TmdbTvDetails,
)
from app.providers.base import BaseProvider

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class TmdbProvider(BaseProvider):
    """Provider adapter for The Movie Database (TMDB) v3 API.

    Args:
        http: Shared HTTP client (handles retries, timeouts and status codes).
        settings: Application settings; supplies the API key and base URL.

    The API key is sent as a query parameter, which is why ``core/logging.py``
    silences ``httpx`` request logging.
    """

    name = tmdb_mapper.PROVIDER_NAME

    def __init__(self, http: HttpClient, settings: Settings) -> None:
        self._http = http
        self._base_url = settings.tmdb_base_url.rstrip("/")
        self._token = settings.tmdb_read_access_token

    @staticmethod
    def _has_value(secret: SecretStr | None) -> bool:
        return secret is not None and bool(secret.get_secret_value().strip())

    @property
    def is_configured(self) -> bool:
        """``True`` when a read access token or an API key is set."""
        return self._has_value(self._token) or self._has_value(self._api_key)

    # ---------- Public API ----------

    async def search(
        self,
        title: str,
        *,
        year: int | None = None,
        media_type: MediaType | None = None,
    ) -> list[SearchResult]:
        """Search TMDB by title.

        Picks the endpoint from ``media_type``: ``/search/movie``,
        ``/search/tv``, or ``/search/multi`` when no type is given. Multi search
        has no year filter, so the year is applied here afterwards.

        Args:
            title: Title text, already sanitised by the caller.
            year: Release year (movies) or first-air year (series).
            media_type: Restrict to movies or series.

        Returns:
            Matches in TMDB's relevance order. Empty for no matches, and always
            empty for ``MediaType.EPISODE`` because TMDB can't search episodes
            by title.

        Raises:
            ProviderAuthError: No API key configured, or TMDB rejected it.
            ProviderBadResponse: TMDB returned an unexpected payload.
            ProviderError: Any other upstream failure (timeout, 5xx, rate limit).
        """
        if media_type is MediaType.EPISODE:
            return []

        if media_type is MediaType.MOVIE:
            path, default_kind, extra = "/search/movie", "movie", {"year": year}
        elif media_type is MediaType.SERIES:
            path, default_kind, extra = "/search/tv", "tv", {"first_air_date_year": year}
        else:
            path, default_kind, extra = "/search/multi", None, {}

        data = await self._fetch(path, {"query": title, "include_adult": "false", **extra})
        raw = self._validate(TmdbSearchResponse, data, "search")
        results = tmdb_mapper.map_search_response(raw, default_kind)

        if year is not None and default_kind is None:
            results = [r for r in results if r.year == year]
        return results

    async def get_details(self, provider_id: str) -> Media:
        """Fetch full details for one title.

        Args:
            provider_id: A prefixed TMDB ID: ``movie:27205``, ``tv:1396`` or
                ``tv:1396:1:2`` (series, season, episode). These are the
                ``source_id`` values returned by ``search()``.

        Returns:
            A ``Movie``, ``Series`` or ``Episode``. Episode lookups make two
            concurrent requests because the parent series' IMDb ID is not part
            of the episode response.

        Raises:
            ProviderNotFound: The ID is malformed, or TMDB has no such item.
            ProviderAuthError: No API key configured, or TMDB rejected it.
            ProviderBadResponse: TMDB's data failed validation.
            ProviderError: Any other upstream failure.
        """
        kind, tmdb_id, season, episode = self._parse_id(provider_id)

        try:
            if kind == "movie":
                data = await self._fetch(f"/movie/{tmdb_id}")
                return tmdb_mapper.map_movie(self._validate(TmdbMovieDetails, data, "movie details"))

            if season is None or episode is None:
                data = await self._fetch(f"/tv/{tmdb_id}", {"append_to_response": "external_ids"})
                return tmdb_mapper.map_tv(self._validate(TmdbTvDetails, data, "tv details"))

            episode_data, series_ids_data = await asyncio.gather(
                self._fetch(
                    f"/tv/{tmdb_id}/season/{season}/episode/{episode}",
                    {"append_to_response": "external_ids"},
                ),
                self._fetch(f"/tv/{tmdb_id}/external_ids"),
            )
            return tmdb_mapper.map_episode(
                self._validate(TmdbEpisode, episode_data, "episode details"),
                series_id=tmdb_id,
                season=season,
                episode=episode,
                series_ids=self._validate(TmdbExternalIds, series_ids_data, "external ids"),
            )
        except ValidationError as exc:
            # The mapped data failed our strict domain models.
            raise ProviderBadResponse(self.name, "details failed domain validation") from exc

    # ---------- Internals ----------

    async def _fetch(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET a TMDB path and return the JSON object.

        Authenticates with the bearer token when configured, otherwise falls
        back to the ``api_key`` query parameter. Drops ``None`` parameters.

        Raises:
            ProviderAuthError: If no credentials are configured.
            ProviderBadResponse: If the body is not a JSON object.
        """
        if not self.is_configured:
            raise ProviderAuthError(self.name, "credentials not configured")

        query = {k: v for k, v in (params or {}).items() if v is not None}
        headers = {"Accept": "application/json"}

        if self._has_value(self._token):
            headers["Authorization"] = f"Bearer {self._token.get_secret_value().strip()}"  # type: ignore[union-attr]
        else:
            query["api_key"] = self._api_key.get_secret_value().strip()  # type: ignore[union-attr]

        data = await self._http.get_json(self.name, f"{self._base_url}{path}", params=query, headers=headers)
        if not isinstance(data, dict):
            raise ProviderBadResponse(self.name, "expected a JSON object")
        return data

    def _validate(self, model: type[T], data: dict[str, Any], what: str) -> T:
        """Parse ``data`` into a raw model.

        Args:
            model: The raw model class to build.
            data: The JSON object from TMDB.
            what: Short label used in the error message, e.g. ``"search"``.

        Raises:
            ProviderBadResponse: If the payload doesn't fit the model.
        """
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            raise ProviderBadResponse(self.name, f"unexpected {what} payload") from exc

    def _parse_id(self, provider_id: str) -> tuple[str, int, int | None, int | None]:
        """Split a prefixed ID into ``(kind, tmdb_id, season, episode)``.

        ``season`` and ``episode`` are ``None`` unless the ID has four parts.

        Raises:
            ProviderNotFound: If the format isn't one of the three accepted forms.
        """
        parts = provider_id.strip().split(":")
        try:
            if parts[0] == "movie" and len(parts) == 2:
                return "movie", int(parts[1]), None, None
            if parts[0] == "tv" and len(parts) == 2:
                return "tv", int(parts[1]), None, None
            if parts[0] == "tv" and len(parts) == 4:
                return "tv", int(parts[1]), int(parts[2]), int(parts[3])
        except ValueError:
            pass
        raise ProviderNotFound(self.name, f"invalid id format: {provider_id!r}")
