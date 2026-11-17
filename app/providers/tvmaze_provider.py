"""TVMaze adapter: series search, series details and episode names.

TVMaze is the preferred source for TV names and episode titles. It needs no API
key. It does not supply posters in this application; TMDB does.

Pipeline position:
    controller -> TvmazeProvider (this file) -> HttpClient -> TVMaze
                                             -> tvmaze_mapper -> domain models

Errors:
    Everything raised is a ``ProviderError`` or ``ValidationFailed``. TVMaze
    uses real HTTP status codes, which ``HttpClient`` already translates.
    Note that TVMaze rate-limits to roughly 20 calls per 10 seconds per IP.
"""

import asyncio
import logging
from typing import Any, TypeVar

from pydantic import BaseModel, TypeAdapter, ValidationError

from app.core.config import Settings
from app.core.http_client import HttpClient
from app.exceptions.errors import ProviderBadResponse, ProviderNotFound
from app.mappers import tvmaze_mapper
from app.models.domain.media import Media, MediaType
from app.models.domain.search_result import SearchResult
from app.models.domain.season import SeasonEpisodesResponse, SeasonsResponse
from app.models.raw.tvmaze import TvmazeEpisode, TvmazeSearchItem, TvmazeShow
from app.providers.base import BaseProvider
from app.validators.common import validate_season_episode

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_SEARCH_ADAPTER = TypeAdapter(list[TvmazeSearchItem])
_EPISODES_ADAPTER = TypeAdapter(list[TvmazeEpisode])


class TvmazeProvider(BaseProvider):
    """Provider adapter for the TVMaze public API.

    Args:
        http: Shared HTTP client (retries, timeouts, status-code translation).
        settings: Application settings; supplies the base URL.
    """

    name = tvmaze_mapper.PROVIDER_NAME
    name_types = frozenset({MediaType.SERIES, MediaType.EPISODE})
    # poster_types stays empty: posters come from TMDB.

    def __init__(self, http: HttpClient, settings: Settings) -> None:
        self._http = http
        self._base_url = settings.tvmaze_base_url.rstrip("/")

    @property
    def is_configured(self) -> bool:
        """Always ``True``: TVMaze needs no credentials."""
        return True

    # ---------- Public API ----------

    async def search(
        self,
        title: str,
        *,
        year: int | None = None,
        media_type: MediaType | None = None,
    ) -> list[SearchResult]:
        """Search TVMaze for TV series by name.

        Args:
            title: Title text, already sanitised by the caller.
            year: Premiere year. TVMaze has no year filter, so it is applied
                to the results afterwards.
            media_type: Only ``series`` (or ``None``) returns anything. Movies
                and episodes return an empty list.

        Returns:
            Matches in TVMaze's relevance order.

        Raises:
            ProviderBadResponse: TVMaze returned an unexpected payload.
            ProviderError: Any upstream failure (timeout, 5xx, rate limit).
        """
        if media_type not in (None, MediaType.SERIES):
            return []

        data = await self._fetch("/search/shows", {"q": title})
        items = self._validate_search(data)
        results = tvmaze_mapper.map_search_response(items)

        if year is not None:
            results = [r for r in results if r.year == year]
        return results

    async def get_details(self, provider_id: str) -> Media:
        """Fetch a series or a single episode.

        Args:
            provider_id: ``show:674`` for a series, or ``show:674:1:3`` for
                season 1, episode 3.

        Returns:
            A ``Series`` or an ``Episode``. Episode lookups make two concurrent
            requests, because the episode payload lacks the show's IMDb ID.

        Raises:
            ProviderNotFound: Malformed ID, or TVMaze has no such item.
            ValidationFailed: Season or episode number out of range.
            ProviderBadResponse: TVMaze's data failed validation.
        """
        show_id, season, episode = self._parse_id(provider_id)

        try:
            if season is None or episode is None:
                data = await self._fetch(f"/shows/{show_id}", {"embed": "seasons"})
                return tvmaze_mapper.map_show(self._validate(TvmazeShow, data, "show details"))

            episode_data, show_data = await asyncio.gather(
                self._fetch(f"/shows/{show_id}/episodebynumber", {"season": season, "number": episode}),
                self._fetch(f"/shows/{show_id}"),
            )
            show = self._validate(TvmazeShow, show_data, "show details")
            return tvmaze_mapper.map_episode(
                self._validate(TvmazeEpisode, episode_data, "episode details"),
                show_id=show_id,
                season=season,
                episode=episode,
                series_imdb_id=show.externals.imdb if show.externals else None,
            )
        except ValidationError as exc:
            logger.error("Domain validation failed: %s", exc.errors(include_input=False))
            raise ProviderBadResponse(self.name, "details failed domain validation") from exc

    async def get_seasons(self, provider_id: str) -> SeasonsResponse:
        """Fetch a show and all its seasons in one request.

        Args:
            provider_id: ``show:674``, a ``source_id`` from ``search()``.

        Raises:
            ProviderNotFound: Malformed ID, or TVMaze has no such show.
            ProviderBadResponse: TVMaze's data failed validation.
        """
        show_id = self._parse_prefixed_id(provider_id, "show")
        data = await self._fetch(f"/shows/{show_id}", {"embed": "seasons"})
        show = self._validate(TvmazeShow, data, "show details")
        try:
            return SeasonsResponse(
                series=tvmaze_mapper.map_show(show),
                seasons=tvmaze_mapper.map_seasons(show),
            )
        except ValidationError as exc:
            logger.error("Domain validation failed: %s", exc.errors(include_input=False))
            raise ProviderBadResponse(self.name, "seasons failed domain validation") from exc

    async def get_season_episodes(self, season_id: str) -> SeasonEpisodesResponse:
        """Fetch the episode list of one season.

        Args:
            season_id: ``season:2696``, a ``source_id`` from ``get_seasons()``.

        Raises:
            ProviderNotFound: Malformed ID, or TVMaze has no such season.
            ProviderBadResponse: TVMaze's data failed validation.
        """
        numeric_id = self._parse_prefixed_id(season_id, "season")
        data = await self._fetch(f"/seasons/{numeric_id}/episodes")
        try:
            raw_episodes = _EPISODES_ADAPTER.validate_python(data)
            episodes = tvmaze_mapper.map_episode_list(raw_episodes)
        except ValidationError as exc:
            raise ProviderBadResponse(self.name, "unexpected episode list payload") from exc
        return SeasonEpisodesResponse(season_id=f"season:{numeric_id}", count=len(episodes), episodes=episodes)

    # ---------- Internals ----------

    async def _fetch(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET a TVMaze path and return the decoded JSON (an object or a list).

        Drops ``None`` parameters. No authentication is needed.
        """
        query = {k: v for k, v in (params or {}).items() if v is not None}
        return await self._http.get_json(
            self.name,
            f"{self._base_url}{path}",
            params=query,
            headers={"Accept": "application/json"},
        )

    def _validate(self, model: type[T], data: Any, what: str) -> T:
        """Parse ``data`` into a raw model.

        Raises:
            ProviderBadResponse: If the payload doesn't fit the model.
        """
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            raise ProviderBadResponse(self.name, f"unexpected {what} payload") from exc

    def _validate_search(self, data: Any) -> list[TvmazeSearchItem]:
        """Parse the search response, which is a JSON list.

        Raises:
            ProviderBadResponse: If it isn't a list of search hits.
        """
        try:
            return _SEARCH_ADAPTER.validate_python(data)
        except ValidationError as exc:
            raise ProviderBadResponse(self.name, "unexpected search payload") from exc

    def _parse_id(self, provider_id: str) -> tuple[int, int | None, int | None]:
        """Split an ID into ``(show_id, season, episode)``.

        Accepts ``show:<id>`` and ``show:<id>:<season>:<episode>``.

        Raises:
            ProviderNotFound: For any other format.
            ValidationFailed: If season or episode is out of range.
        """
        parts = provider_id.strip().split(":")
        try:
            if parts[0] == "show" and len(parts) == 2:
                return int(parts[1]), None, None
            if parts[0] == "show" and len(parts) == 4:
                show_id, season, episode = int(parts[1]), int(parts[2]), int(parts[3])
                validate_season_episode(season, episode)
                return show_id, season, episode
        except ValueError:
            pass
        raise ProviderNotFound(self.name, f"invalid id format: {provider_id!r}")

    def _parse_prefixed_id(self, provider_id: str, prefix: str) -> int:
        """Extract the number from ``<prefix>:<id>``.

        Raises:
            ProviderNotFound: For any other format.
        """
        head, _, number = provider_id.strip().partition(":")
        if head == prefix and number.isdigit():
            return int(number)
        raise ProviderNotFound(self.name, f"invalid id format: {provider_id!r}; expected '{prefix}:<number>'")
