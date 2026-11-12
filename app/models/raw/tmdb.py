"""Permissive models for TMDB v3 API responses.

These describe what TMDB sends, not what the application uses. Unknown fields
are ignored and almost everything is optional, so a surprising payload does not
fail here. Strictness is applied later, when ``tmdb_mapper`` converts these
into the models in ``models/domain``.

Pipeline position:
    TMDB JSON -> models/raw/tmdb.py (this file) -> tmdb_mapper -> models/domain

TMDB quirks that explain several fields:
    * Dates are strings and may be ``""`` for unreleased titles.
    * ``vote_average`` is ``0.0`` when there are no votes.
    * Image fields are paths (``/abc.jpg``), not URLs.
    * Movies and TV shows use different field names (``title`` vs ``name``).
"""

from pydantic import BaseModel, ConfigDict, Field


class TmdbModel(BaseModel):
    """Base for all TMDB raw models; ignores fields we don't declare."""

    model_config = ConfigDict(extra="ignore")


class TmdbGenre(TmdbModel):
    """A genre entry such as ``{"id": 28, "name": "Action"}``."""

    id: int | None = None
    name: str | None = None


class TmdbSearchItem(TmdbModel):
    """One hit from a TMDB search endpoint.

    ``/search/multi`` also returns people, so ``media_type`` can be ``"person"``;
    the mapper filters those out.

    Attributes:
        media_type: ``"movie"``, ``"tv"`` or ``"person"``. Only set by
            ``/search/multi``; ``/search/movie`` and ``/search/tv`` omit it.
        title: Movie title. Absent for TV shows.
        name: TV show or person name. Absent for movies.
        release_date: Movies only. ``""`` when unreleased.
        first_air_date: TV only. ``""`` when unaired.
        poster_path: Path to append to the image base URL, not a full URL.
    """

    id: int
    media_type: str | None = None
    title: str | None = None
    name: str | None = None
    original_title: str | None = None
    original_name: str | None = None
    release_date: str | None = None
    first_air_date: str | None = None
    overview: str | None = None
    poster_path: str | None = None
    vote_average: float | None = None
    genre_ids: list[int] = Field(default_factory=list)


class TmdbSearchResponse(TmdbModel):
    """Paged envelope returned by every TMDB search endpoint."""

    page: int = 1
    results: list[TmdbSearchItem] = Field(default_factory=list)
    total_pages: int = 0
    total_results: int = 0


class TmdbExternalIds(TmdbModel):
    """IDs of the same title in other systems.

    Returned by ``/tv/{id}/external_ids`` or by adding
    ``append_to_response=external_ids`` to a details request.
    """

    imdb_id: str | None = None
    tvdb_id: int | None = None


class TmdbMovieDetails(TmdbModel):
    """Response of ``/movie/{id}``.

    Attributes:
        runtime: Minutes. May be ``0`` or ``None`` when unknown.
        vote_average: ``0.0`` means "no votes", not a real rating.
    """

    id: int
    imdb_id: str | None = None
    title: str | None = None
    original_title: str | None = None
    release_date: str | None = None
    runtime: int | None = None
    overview: str | None = None
    poster_path: str | None = None
    vote_average: float | None = None
    genres: list[TmdbGenre] = Field(default_factory=list)


class TmdbTvDetails(TmdbModel):
    """Response of ``/tv/{id}``.

    Attributes:
        status: Free text such as ``"Returning Series"``, ``"Ended"`` or
            ``"Canceled"``.
        external_ids: Only present when the request used
            ``append_to_response=external_ids``. TMDB does not include the
            IMDb ID in the base TV response.
    """

    id: int
    name: str | None = None
    original_name: str | None = None
    first_air_date: str | None = None
    last_air_date: str | None = None
    status: str | None = None
    number_of_seasons: int | None = None
    number_of_episodes: int | None = None
    overview: str | None = None
    poster_path: str | None = None
    vote_average: float | None = None
    genres: list[TmdbGenre] = Field(default_factory=list)
    external_ids: TmdbExternalIds | None = None


class TmdbEpisode(TmdbModel):
    """Response of ``/tv/{id}/season/{n}/episode/{m}``.

    Attributes:
        still_path: Path to the episode's screenshot, used as its image.
        external_ids: Only present with ``append_to_response=external_ids``.
            These are the episode's own IDs, not the series'.
    """

    id: int
    name: str | None = None
    overview: str | None = None
    air_date: str | None = None
    season_number: int | None = None
    episode_number: int | None = None
    runtime: int | None = None
    vote_average: float | None = None
    still_path: str | None = None
    external_ids: TmdbExternalIds | None = None
