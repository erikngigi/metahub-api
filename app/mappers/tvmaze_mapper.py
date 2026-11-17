"""Converts raw TVMaze models into the clean domain models.

Every function here is pure: no network, no I/O, no state.

Pipeline position:
    models/raw/tvmaze -> tvmaze_mapper (this file) -> models/domain

Source IDs:
    * ``show:674``       a series
    * ``show:674:1:3``   series 674, season 1, episode 3

Search items that can't be used are dropped silently. Details that can't be
used raise ``ProviderBadResponse``.
"""

import html
import re
from datetime import date

from app.exceptions.errors import ProviderBadResponse
from app.models.domain.media import Episode, MediaStatus, MediaType, Series
from app.models.domain.search_result import SearchResult
from app.models.domain.season import EpisodeListItem, Season
from app.models.raw.tvmaze import (
    TvmazeEpisode,
    TvmazeExternals,
    TvmazeImage,
    TvmazeSearchItem,
    TvmazeSeason,
    TvmazeShow,
)

PROVIDER_NAME = "tvmaze"

_STATUS_MAP = {
    "running": MediaStatus.ONGOING,
    "ended": MediaStatus.ENDED,
    "in development": MediaStatus.UPCOMING,
    # "To Be Determined" is deliberately absent: it means unknown, so it maps to None.
}

_TAG = re.compile(r"<[^>]+>")
_BLANK_LINES = re.compile(r"\n{3,}")


# ---------- Cleaning helpers ----------


def _clean(value: str | None) -> str | None:
    """Strip whitespace and turn empty strings into ``None``."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def _strip_html(value: str | None) -> str | None:
    """Convert TVMaze's HTML summary to plain text, keeping paragraph breaks."""
    if not value:
        return None
    text = value.replace("</p>", "\n\n").replace("<br>", "\n").replace("<br/>", "\n")
    text = html.unescape(_TAG.sub("", text))
    text = _BLANK_LINES.sub("\n\n", text).strip()
    return text or None


def _parse_year(date: str | None) -> int | None:
    """Extract the year from ``YYYY-MM-DD``; ``None`` for empty or malformed values."""
    cleaned = _clean(date)
    if not cleaned or len(cleaned) < 4 or not cleaned[:4].isdigit():
        return None
    return int(cleaned[:4])


def _image_url(image: TvmazeImage | None) -> str | None:
    """Prefer the medium image (smaller download); fall back to the original."""
    if image is None:
        return None
    return _clean(image.original) or _clean(image.medium)


def _rating(value: float | None) -> float | None:
    """Round to one decimal; ``None`` and ``0`` both mean no rating."""
    return round(value, 1) if value else None


def _map_status(value: str | None) -> MediaStatus | None:
    """Translate TVMaze's status words; unrecognised values become ``None``."""
    return _STATUS_MAP.get((value or "").strip().lower())


def _external_ids(show_id: int, externals: TvmazeExternals | None) -> dict[str, str]:
    """Build the ``external_ids`` dict, leaving out missing IDs."""
    ids = {"tvmaze": str(show_id)}
    if externals:
        if externals.imdb:
            ids["imdb"] = externals.imdb
        if externals.thetvdb:
            ids["thetvdb"] = str(externals.thetvdb)
        if externals.tvrage:
            ids["tvrage"] = str(externals.tvrage)
    return ids


def _total_episodes(seasons: list[TvmazeSeason]) -> int | None:
    """Sum the planned episodes, or ``None`` if any season's length is unknown."""
    if not seasons or any(s.episode_order is None for s in seasons):
        return None
    return sum(s.episode_order for s in seasons) or None  # type: ignore[misc]


# ---------- Search ----------


def map_search_item(item: TvmazeSearchItem) -> SearchResult | None:
    """Convert one search hit into a ``SearchResult``, or ``None`` if it has no name."""
    show = item.show
    title = _clean(show.name)
    if not title:
        return None

    return SearchResult(
        source=PROVIDER_NAME,
        source_id=f"show:{show.id}",
        imdb_id=_clean(show.externals.imdb) if show.externals else None,
        media_type=MediaType.SERIES,
        title=title,
        year=_parse_year(show.premiered),
        poster_url=_image_url(show.image),
    )


def map_search_response(items: list[TvmazeSearchItem]) -> list[SearchResult]:
    """Convert a search response, skipping unusable items. Keeps TVMaze's relevance order."""
    results = (map_search_item(i) for i in items)
    return [r for r in results if r is not None]


# ---------- Details ----------


def map_show(raw: TvmazeShow) -> Series:
    """Convert a show into a ``Series``.

    Season and episode totals come from the embedded seasons, so the request
    must have used ``?embed=seasons``; otherwise they stay ``None``.

    Raises:
        ProviderBadResponse: If the show has no name.
    """
    title = _clean(raw.name)
    if not title:
        raise ProviderBadResponse(PROVIDER_NAME, "show details missing name")

    status = _map_status(raw.status)
    has_ended = status is MediaStatus.ENDED
    seasons = raw.embedded.seasons if raw.embedded else []

    return Series(
        source=PROVIDER_NAME,
        source_id=f"show:{raw.id}",
        external_ids=_external_ids(raw.id, raw.externals),
        title=title,
        year=_parse_year(raw.premiered),
        plot=_strip_html(raw.summary),
        genres=[g for g in raw.genres if g],
        rating=_rating(raw.rating.average if raw.rating else None),
        poster_url=_image_url(raw.image),
        end_year=_parse_year(raw.ended) if has_ended else None,
        total_seasons=len(seasons) or None,
        total_episodes=_total_episodes(seasons),
        status=status,
    )


def map_episode(
    raw: TvmazeEpisode,
    *,
    show_id: int,
    season: int,
    episode: int,
    series_imdb_id: str | None = None,
) -> Episode:
    """Convert an episode into an ``Episode``.

    Season and episode numbers come from the request, so they always match the
    ID that was asked for.

    Raises:
        ProviderBadResponse: If the episode has no name.
    """
    title = _clean(raw.name)
    if not title:
        raise ProviderBadResponse(PROVIDER_NAME, "episode details missing name")

    return Episode(
        source=PROVIDER_NAME,
        source_id=f"show:{show_id}:{season}:{episode}",
        external_ids={"tvmaze": str(raw.id)},
        title=title,
        year=_parse_year(raw.airdate),
        plot=_strip_html(raw.summary),
        rating=_rating(raw.rating.average if raw.rating else None),
        poster_url=_image_url(raw.image),
        series_imdb_id=_clean(series_imdb_id),
        season=season,
        episode=episode,
    )


# ---------- Seasons and episode lists ----------


def _parse_date(value: str | None) -> date | None:
    """Parse ``YYYY-MM-DD``; ``None`` for empty or malformed values."""
    cleaned = _clean(value)
    if not cleaned:
        return None
    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        return None


def map_season(raw: TvmazeSeason) -> Season:
    """Convert one raw season into a ``Season``."""
    network = (raw.network.name if raw.network else None) or (raw.web_channel.name if raw.web_channel else None)
    return Season(
        source=PROVIDER_NAME,
        source_id=f"season:{raw.id}",
        season_number=raw.number,
        name=_clean(raw.name),
        episode_count=raw.episode_order,
        premiere_date=_parse_date(raw.premiere_date),
        end_date=_parse_date(raw.end_date),
        network=_clean(network),
        plot=_strip_html(raw.summary),
        poster_url=_image_url(raw.image),
    )


def map_seasons(show: TvmazeShow) -> list[Season]:
    """Map the seasons embedded in a show, sorted by season number (unknown last)."""
    raw_seasons = show.embedded.seasons if show.embedded else []
    ordered = sorted(raw_seasons, key=lambda s: (s.number is None, s.number or 0))
    return [map_season(s) for s in ordered]


def map_episode_item(raw: TvmazeEpisode) -> EpisodeListItem | None:
    """Convert one episode into a list item, or ``None`` if it has no name."""
    name = _clean(raw.name)
    if not name:
        return None
    return EpisodeListItem(
        source=PROVIDER_NAME,
        episode_id=str(raw.id),
        season=raw.season,
        number=raw.number,
        type=_clean(raw.type),
        name=name,
        air_date=_parse_date(raw.airdate),
        runtime_minutes=raw.runtime or None,
        rating=_rating(raw.rating.average if raw.rating else None),
    )


def map_episode_list(items: list[TvmazeEpisode]) -> list[EpisodeListItem]:
    """Convert an episode list, skipping unnamed entries and keeping TVMaze's order."""
    mapped = (map_episode_item(i) for i in items)
    return [m for m in mapped if m is not None]
