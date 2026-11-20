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
from app.models.domain.media import Media, MediaType, Movie, Series
from app.models.domain.search_result import SearchResult
from app.models.domain.season import SeasonDetailsResponse
from app.models.raw.tmdb import (
    TmdbMovieDetails,
    TmdbSearchResponse,
    TmdbSeasonDetails,
    TmdbTvDetails,
)
from app.providers.base import BaseProvider
from app.services.naming import format_episode_label

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

        # ---------- Details: movies ----------

    async def get_movie(self, movie_id: int) -> Movie:
        """Fetch full details for one movie.

        Calls ``GET /movie/{movie_id}``.

        Raises:
            ProviderNotFound: TMDB has no such movie.
            ProviderBadResponse: TMDB's data failed validation.
        """
        data = await self._fetch(f"/movie/{movie_id}")
        raw = self._validate(TmdbMovieDetails, data, "movie details")
        try:
            return tmdb_mapper.map_movie(raw)
        except ValidationError as exc:
            self._log_domain_error(exc)
            raise ProviderBadResponse(self.name, "movie failed domain validation") from exc

    # ---------- Details: shows ----------

    async def get_show(self, show_id: int) -> Series:
        """Fetch full details for one TV show.

        Calls ``GET /tv/{show_id}?append_to_response=external_ids``. The extra
        parameter is what supplies the IMDb ID, which TMDB omits by default.

        Raises:
            ProviderNotFound: TMDB has no such show.
            ProviderBadResponse: TMDB's data failed validation.
        """
        data = await self._fetch(f"/tv/{show_id}", {"append_to_response": "external_ids"})
        raw = self._validate(TmdbTvDetails, data, "tv details")
        try:
            return tmdb_mapper.map_tv(raw)
        except ValidationError as exc:
            self._log_domain_error(exc)
            raise ProviderBadResponse(self.name, "show failed domain validation") from exc

    async def get_show_season(self, show_id: int, season: int) -> SeasonDetailsResponse:
        """Fetch one season of a TV show, with its episode list.

        Calls ``GET /tv/{show_id}/season/{season}``. One request returns both
        the season's details and every episode in it.

        Raises:
            ProviderNotFound: TMDB has no such show or season.
            ProviderBadResponse: TMDB's data failed validation.
        """
        data = await self._fetch(f"/tv/{show_id}/season/{season}")
        raw = self._validate(TmdbSeasonDetails, data, "season details")
        show = await self.get_show(show_id)

        try:
            return tmdb_mapper.map_season_details(raw, show_id=show_id, season=season, title=show.title)
        except ValidationError as exc:
            self._log_domain_error(exc)
            raise ProviderBadResponse(self.name, "season failed domain validation") from exc

    # ---------- Generic entry point ----------

    async def get_details(self, provider_id: str) -> Media:
        """Dispatch a prefixed ID to the movie or show method.

        Accepts ``movie:27205`` and ``tv:1396``. Seasons are served by
        ``get_show_season`` and are not available through this method.

        Raises:
            ProviderNotFound: The ID is malformed, or TMDB has no such item.
        """
        kind, tmdb_id = self._parse_id(provider_id)
        if kind == "movie":
            return await self.get_movie(tmdb_id)
        return await self.get_show(tmdb_id)

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

    def _log_domain_error(self, exc: ValidationError) -> None:
        """Log which field failed our strict models, without logging the data."""
        logger.error("TMDB domain validation failed: %s", exc.errors(include_input=False))

    def _parse_id(self, provider_id: str) -> tuple[str, int]:
        """Split ``movie:<id>`` or ``tv:<id>`` into ``(kind, tmdb_id)``.

        Raises:
            ProviderNotFound: If the format isn't one of the two accepted forms.
        """
        kind, _, number = provider_id.strip().partition(":")
        if kind in ("movie", "tv") and number.isdigit():
            return kind, int(number)
        raise ProviderNotFound(self.name, f"invalid id format: {provider_id!r}")
