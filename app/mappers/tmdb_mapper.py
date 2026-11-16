"""Converts raw TMDB models into the clean domain models.

Every function here is pure: no network, no I/O, no state. That makes them easy
to unit test with saved JSON from ``tests/fixtures/tmdb``.

Pipeline position:
    models/raw/tmdb -> tmdb_mapper (this file) -> models/domain

Source IDs are prefixed with their kind because TMDB movie and TV IDs share
number ranges:
    * ``movie:27205``      a movie
    * ``tv:1396``          a series
    * ``tv:1396:1:2``      series 1396, season 1, episode 2

Search items that can't be used (people, missing title) are dropped silently.
Details that can't be used raise ``ProviderBadResponse``.
"""

from app.exceptions.errors import ProviderBadResponse
from app.models.domain.media import Episode, Media, MediaStatus, MediaType, Movie, Series
from app.models.domain.search_result import SearchResult
from app.models.raw.tmdb import (
    TmdbEpisode,
    TmdbExternalIds,
    TmdbGenre,
    TmdbMovieDetails,
    TmdbSearchItem,
    TmdbSearchResponse,
    TmdbTvDetails,
)

PROVIDER_NAME = "tmdb"
IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"

_KIND_TO_TYPE = {"movie": MediaType.MOVIE, "tv": MediaType.SERIES}
_ENDED_STATUSES = {"ended", "canceled", "cancelled"}
_STATUS_MAP = {
    "returning series": MediaStatus.ONGOING,
    "in production": MediaStatus.UPCOMING,
    "planned": MediaStatus.UPCOMING,
    "pilot": MediaStatus.UPCOMING,
    "ended": MediaStatus.ENDED,
    "canceled": MediaStatus.CANCELLED,
    "cancelled": MediaStatus.CANCELLED,
}

# ---------- Cleaning helpers ----------


def _clean(value: str | None) -> str | None:
    """Strip whitespace and turn empty strings into ``None``."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def _parse_year(date: str | None) -> int | None:
    """Extract the year from a ``YYYY-MM-DD`` string.

    Returns ``None`` for ``None``, ``""`` (TMDB's value for unreleased
    titles) or anything not starting with four digits.
    """
    cleaned = _clean(date)
    if not cleaned or len(cleaned) < 4 or not cleaned[:4].isdigit():
        return None
    return int(cleaned[:4])


def _image_url(path: str | None) -> str | None:
    """Turn a TMDB image path into an absolute URL, or ``None`` if empty."""
    cleaned = _clean(path)
    return f"{IMAGE_BASE_URL}{cleaned}" if cleaned else None


def _rating(value: float | None) -> float | None:
    """Round to one decimal. ``0.0`` becomes ``None`` because TMDB uses it for "no votes"."""
    return round(value, 1) if value else None


def _genre_names(genres: list[TmdbGenre]) -> list[str]:
    """Return the names of genres that have one."""
    return [g.name for g in genres if g.name]


def _imdb_id(external_ids: TmdbExternalIds | None) -> str | None:
    """Return the cleaned IMDb ID from an external-ids block, if present."""
    return _clean(external_ids.imdb_id) if external_ids else None


def _map_status(value: str | None) -> MediaStatus | None:
    """Translate TMDB's free-text status into ``MediaStatus``.

    Returns ``None`` for missing or unrecognised values, so a new TMDB
    status never breaks a request.
    """
    return _STATUS_MAP.get((value or "").strip().lower())


# ---------- Search ----------


def map_search_item(item: TmdbSearchItem, default_kind: str | None = None) -> SearchResult | None:
    """Convert one search hit into a ``SearchResult``.

    Args:
        item: A raw hit from any TMDB search endpoint.
        default_kind: ``"movie"`` or ``"tv"``. Needed for ``/search/movie`` and
            ``/search/tv``, whose items carry no ``media_type`` of their own.

    Returns:
        The mapped result, or ``None`` for people, unknown kinds and items
        without a title. ``imdb_id`` is always ``None`` because TMDB search
        does not return it.
    """
    kind = item.media_type or default_kind
    media_type = _KIND_TO_TYPE.get(kind or "")
    if media_type is None:
        return None

    if kind == "movie":
        title, date = _clean(item.title), item.release_date
    else:
        title, date = _clean(item.name), item.first_air_date
    if not title:
        return None

    return SearchResult(
        source=PROVIDER_NAME,
        source_id=f"{kind}:{item.id}",
        imdb_id=None,
        media_type=media_type,
        title=title,
        year=_parse_year(date),
        poster_url=_image_url(item.poster_path),
    )


def map_search_response(raw: TmdbSearchResponse, default_kind: str | None = None) -> list[SearchResult]:
    """Convert a whole search response, skipping unusable items.

    Args:
        raw: The validated search envelope.
        default_kind: Passed through to ``map_search_item``.

    Returns:
        Results in TMDB's original order.
    """
    results = (map_search_item(item, default_kind) for item in raw.results)
    return [r for r in results if r is not None]


# ---------- Details ----------


def map_movie(raw: TmdbMovieDetails) -> Movie:
    """Convert movie details into a ``Movie``.

    Raises:
        ProviderBadResponse: If the movie has no title.
    """
    title = _clean(raw.title)
    if not title:
        raise ProviderBadResponse(PROVIDER_NAME, "movie details missing title")

    return Movie(
        source=PROVIDER_NAME,
        source_id=f"movie:{raw.id}",
        imdb_id=_clean(raw.imdb_id),
        title=title,
        year=_parse_year(raw.release_date),
        plot=_clean(raw.overview),
        genres=_genre_names(raw.genres),
        rating=_rating(raw.vote_average),
        poster_url=_image_url(raw.poster_path),
        runtime_minutes=raw.runtime or None,
    )


def map_tv(raw: TmdbTvDetails) -> Series:
    """Convert TV details into a ``Series``.

    ``end_year`` is only set when the status says the show has finished, since
    ``last_air_date`` is just the latest episode for a running show. The IMDb ID
    is only filled in if the request included ``external_ids``.

    Raises:
        ProviderBadResponse: If the show has no name.
    """
    title = _clean(raw.name)
    if not title:
        raise ProviderBadResponse(PROVIDER_NAME, "tv details missing name")

    has_ended = (raw.status or "").strip().lower() in _ENDED_STATUSES
    return Series(
        source=PROVIDER_NAME,
        source_id=f"tv:{raw.id}",
        imdb_id=_imdb_id(raw.external_ids),
        title=title,
        year=_parse_year(raw.first_air_date),
        plot=_clean(raw.overview),
        genres=_genre_names(raw.genres),
        rating=_rating(raw.vote_average),
        poster_url=_image_url(raw.poster_path),
        end_year=_parse_year(raw.last_air_date) if has_ended else None,
        total_seasons=raw.number_of_seasons or None,
        total_episodes=raw.number_of_episodes or None,
        status=_map_status(raw.status),
    )


def map_episode(
    raw: TmdbEpisode,
    *,
    series_id: int,
    season: int,
    episode: int,
    series_ids: TmdbExternalIds | None = None,
) -> Episode:
    """Convert an episode response into an ``Episode``.

    The season and episode numbers come from the caller (they were part of the
    request) rather than from the payload, so they always match the ID that was
    asked for.

    Args:
        raw: The raw episode details.
        series_id: TMDB ID of the parent series.
        season: Season number requested.
        episode: Episode number requested.
        series_ids: External IDs of the parent series, used for
            ``series_imdb_id``.

    Raises:
        ProviderBadResponse: If the episode has no name.
    """
    title = _clean(raw.name)
    if not title:
        raise ProviderBadResponse(PROVIDER_NAME, "episode details missing name")

    return Episode(
        source=PROVIDER_NAME,
        source_id=f"tv:{series_id}:{season}:{episode}",
        imdb_id=_imdb_id(raw.external_ids),
        title=title,
        original_title=title,
        year=_parse_year(raw.air_date),
        plot=_clean(raw.overview),
        rating=_rating(raw.vote_average),
        poster_url=_image_url(raw.still_path),
        series_imdb_id=_imdb_id(series_ids),
        season=season,
        episode=episode,
    )


def to_media(raw: TmdbMovieDetails | TmdbTvDetails) -> Media:
    """Dispatch to ``map_movie`` or ``map_tv`` based on the raw model's type."""
    return map_movie(raw) if isinstance(raw, TmdbMovieDetails) else map_tv(raw)
