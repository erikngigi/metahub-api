"""Clean, provider-independent models for movies, series and episodes.

Every provider describes the same title differently. Mappers convert each
provider's raw response into the models defined here, so the rest of the
application (merge service, views, client) never sees provider-specific shapes.

Pipeline position:
    models/raw (permissive) -> mapper -> models/domain (strict, this file)

Anime is not a separate media type. It is expressed through the ``is_anime``
flag and extra optional fields, so ``media_type`` filtering keeps working.
"""

from datetime import date
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, model_validator


class MediaType(str, Enum):
    """Format of a piece of media.

    This is the format, not the genre or origin. Anime has no value here
    because an anime can be any of these three; see ``MediaBase.is_anime``.
    """

    MOVIE = "movie"
    SERIES = "series"
    EPISODE = "episode"


class MediaStatus(str, Enum):
    """Current status of a piece of media"""

    UPCOMING = "upcoming"
    ONGOING = "ongoing"
    ENDED = "ended"
    CANCELLED = "cancelled"


class MediaBase(BaseModel):
    """Fields shared by every kind of media.

    Not used directly; ``Movie``, ``Series`` and ``Episode`` extend it.

    Attributes:
        source: Name of the provider that produced this record, e.g. ``"tmdb"``.
        source_id: That provider's own ID. Only unique within ``source``.
        external_ids: IDs in other systems, keyed by lowercase name
            (``imdb``, ``tmdb``, ``tvdb``, ``anilist``, ``mal``, ``anidb``,
            ``kitsu``). Used by the merge service to recognise the same title
            across providers.
        imdb_id: Convenience copy of ``external_ids["imdb"]``, kept in sync.
        alternative_titles: Romaji, English, native and alias titles,
            excluding the main and original titles.
        is_anime: ``True``/``False`` when a mapper is confident, ``None`` when
            unknown. ``None`` is not the same as ``False``.
    """

    # --- Provenance ---
    source: str  # which provider produced this record
    source_id: int  # that provider's ID for the item

    # --- Identifiers ---
    # Known keys: imdb, tmdb, tvdb, anilist, mal, anidb, kitsu
    # external_ids: dict[str, str] = Field(default_factory=dict)
    # imdb_id: str | None = None  # kept for convenience; synced with external_ids["imdb"]

    # --- Titles ---
    title: str
    original_title: str | None = None
    # alternative_titles: list[str] = Field(default_factory=list)  # romaji, English, native, aliases

    # --- Descriptive data ---
    year: int | None = None
    plot: str | None = None
    genres: list[str] = Field(default_factory=list)
    rating: float | None = None
    poster_url: str | None = None

    # --- Classification ---
    is_anime: bool | None = None  # None = unknown; a mapper sets it only when confident

    # @model_validator(mode="after")
    # def _normalise(self) -> "MediaBase":
    #     """Enforce consistency rules after validation.
    #
    #     - Keeps ``imdb_id`` and ``external_ids["imdb"]`` in agreement,
    #       whichever one was supplied.
    #     - Lowercases ``external_ids`` keys and drops empty entries.
    #     - Removes duplicate alternative titles (case-insensitive) and any that
    #       repeat ``title`` or ``original_title``, preserving order.
    #
    #     Mutates ``self`` in place. This is safe only while
    #     ``validate_assignment`` is off.
    #     """
    #
    #     # Keep imdb_id and external_ids["imdb"] in agreement, in either direction.
    #     ids = {k.strip().lower(): v for k, v in self.external_ids.items() if k.strip() and v}
    #     if self.imdb_id and "imdb" not in ids:
    #         ids["imdb"] = self.imdb_id
    #     elif "imdb" in ids and not self.imdb_id:
    #         self.imdb_id = ids["imdb"]
    #     self.external_ids = ids
    #
    #     # De-duplicate alternative titles (case-insensitive), preserving order,
    #     # and drop any that just repeat the main or original title.
    #     seen = {self.title.casefold()}
    #     if self.original_title:
    #         seen.add(self.original_title.casefold())
    #     unique: list[str] = []
    #     for alt in self.alternative_titles:
    #         alt = alt.strip()
    #         if alt and alt.casefold() not in seen:
    #             seen.add(alt.casefold())
    #             unique.append(alt)
    #     self.alternative_titles = unique
    #     return self


class Movie(MediaBase):
    """A single feature film, including anime films.

    Attributes:
        runtime_minutes: Length in whole minutes; ``None`` if the provider
        doesn't report it.
    """

    media_type: Literal[MediaType.MOVIE] = MediaType.MOVIE
    runtime_minutes: int | None = None


class SeasonSummary(BaseModel):
    """A season as listed in a series response; no episodes.

    Attributes:
        season_number: ``0`` conventionally means specials.
        name: Season title, e.g. ``"Season 1"`` or ``"Specials"``.
        episode_count: Episodes announced by the provider; ``None`` if unknown.
        premiere_date: Date the season started airing.
        plot: Season synopsis; ``None`` when the provider has none.
        poster_url: Absolute season poster URL.
        rating: Out of 10; ``None`` if unrated.
    """

    season_number: int
    name: str | None = None
    episode_count: int | None = None
    premiere_date: date | None = None
    plot: str | None = None
    poster_url: str | None = None
    rating: float | None = None


class Series(MediaBase):
    """A TV show or other episodic work as a whole, not one season or episode.

    Season and episode counts vary between providers, especially for anime,
    where one provider may list one long season and another list four. Treat
    the totals as per-source values, not as facts, until the merge service
    has reconciled them.

    Attributes:
        end_year: Year the series finished. ``None`` while it is still
            running or when the provider doesn't say.
        total_seasons: Number of seasons as counted by ``source``.
        total_episodes: Total episode count across all seasons. A more
            reliable sanity check than ``total_seasons`` for anime.
        status: Whether the series is upcoming, ongoing, ended or cancelled.
    """

    media_type: Literal[MediaType.SERIES] = MediaType.SERIES
    end_year: int | None = None
    total_seasons: int | None = None
    total_episodes: int | None = None
    original_language: str | None = None
    status: MediaStatus | None = None
    seasons: list[SeasonSummary] = Field(default_factory=list)


class Episode(MediaBase):
    """One episode of a series.

    The inherited ``title``, ``year`` and ``plot`` describe the episode, not the
    show. The parent show is identified through ``series_imdb_id``.

    Attributes:
        series_imdb_id: IMDb ID of the parent series, not of this episode.
        season: Season number as defined by ``source``. ``0`` conventionally
            means specials.
        episode: Episode number within ``season``.
        absolute_episode: Continuous count across the whole series, for example
            ``143``. Common for anime, usually ``None`` for Western shows. It is
            separate from ``season`` and ``episode`` because the same episode can
            be ``S05E12`` in one provider and ``143`` in another.
    """

    media_type: Literal[MediaType.EPISODE] = MediaType.EPISODE
    series_imdb_id: str | None = None
    season: int | None = None
    episode: int | None = None
    # Anime and long-running shows are often numbered continuously ("Episode 143")
    # instead of by season. Optional because most Western shows don't use it.
    absolute_episode: int | None = None


Media = Annotated[Union[Movie, Series, Episode], Field(discriminator="media_type")]
