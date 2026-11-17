"""Permissive models for TVMaze API responses.

These describe what TVMaze sends, not what the application uses. Unknown fields
are ignored and almost everything is optional.

Pipeline position:
    TVMaze JSON -> models/raw/tvmaze.py (this file) -> tvmaze_mapper -> models/domain

TVMaze quirks that explain several fields:
    * ``/search/shows`` wraps every show as ``{"score": ..., "show": {...}}``.
    * Missing values are ``null``, not empty strings.
    * ``summary`` contains HTML (``<p>``, ``<b>``).
    * ``status`` uses its own words: ``Running``, ``Ended``, ``To Be Determined``,
      ``In Development``.
    * Images are an object with ``medium`` and ``original`` URLs.
    * ``number`` on an episode can be ``null`` for some specials.
    * ``?embed=seasons`` places the seasons under ``_embedded``.
"""

from pydantic import BaseModel, ConfigDict, Field


class TvmazeModel(BaseModel):
    """Base for all TVMaze raw models; ignores fields we don't declare."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class TvmazeImage(TvmazeModel):
    """Image URLs. ``medium`` is a small portrait/landscape; ``original`` is full size."""

    medium: str | None = None
    original: str | None = None


class TvmazeRating(TvmazeModel):
    """User rating out of 10. ``average`` is ``null`` when there are no votes."""

    average: float | None = None


class TvmazeExternals(TvmazeModel):
    """IDs of the same show in other systems.

    Attributes:
        tvrage: Numeric ID of the defunct TVRage database.
        thetvdb: Numeric TheTVDB ID.
        imdb: IMDb ID such as ``tt1299368``.
    """

    tvrage: int | None = None
    thetvdb: int | None = None
    imdb: str | None = None


class TvmazeNetwork(TvmazeModel):
    """A TV network or web channel; only the name is used."""

    id: int | None = None
    name: str | None = None


class TvmazeSeason(TvmazeModel):
    """One season of a show.

    Attributes:
        id: TVMaze's global season ID (not the season number).
        number: Season number within the show.
        name: Usually ``""``; some seasons have a title.
        episode_order: Planned episode count; ``null`` when not announced.
        premiere_date: ``YYYY-MM-DD`` or ``null``.
        network: Broadcaster; ``null`` for web-only releases.
        web_channel: Streaming service; ``null`` for broadcast shows.
        summary: HTML text; the mapper strips the tags.
    """

    id: int
    number: int | None = None
    name: str | None = None
    episode_order: int | None = Field(default=None, alias="episodeOrder")
    premiere_date: str | None = Field(default=None, alias="premiereDate")
    end_date: str | None = Field(default=None, alias="endDate")
    network: TvmazeNetwork | None = None
    web_channel: TvmazeNetwork | None = Field(default=None, alias="webChannel")
    image: TvmazeImage | None = None
    summary: str | None = None


class TvmazeEmbedded(TvmazeModel):
    """Extra resources included with ``?embed=...``."""

    seasons: list[TvmazeSeason] = Field(default_factory=list)


class TvmazeShow(TvmazeModel):
    """A show, from ``/shows/{id}`` or nested inside a search hit.

    Attributes:
        type: Format such as ``Scripted``, ``Animation`` or ``Reality``.
        status: ``Running``, ``Ended``, ``To Be Determined`` or ``In Development``.
        premiered: ``YYYY-MM-DD`` of the first episode, or ``null``.
        ended: ``YYYY-MM-DD`` of the last episode, or ``null``.
        summary: HTML text; the mapper strips the tags.
        embedded: Present only when the request used ``?embed=seasons``.
    """

    id: int
    name: str | None = None
    type: str | None = None
    language: str | None = None
    genres: list[str] = Field(default_factory=list)
    status: str | None = None
    premiered: str | None = None
    ended: str | None = None
    rating: TvmazeRating | None = None
    externals: TvmazeExternals | None = None
    image: TvmazeImage | None = None
    summary: str | None = None
    embedded: TvmazeEmbedded | None = Field(default=None, alias="_embedded")


class TvmazeSearchItem(TvmazeModel):
    """One hit from ``/search/shows``: a relevance score plus the show."""

    score: float | None = None
    show: TvmazeShow


class TvmazeEpisode(TvmazeModel):
    """An episode, from ``/shows/{id}/episodebynumber`` or an episode list.

    Attributes:
        name: Episode title.
        season: Season number.
        number: Number within the season; ``null`` for some specials.
        type: ``regular``, ``significant_special`` or ``insignificant_special``.
        airdate: ``YYYY-MM-DD``; may be ``""`` or ``null`` for unaired episodes.
        runtime: Minutes, or ``null``.
        summary: HTML text; the mapper strips the tags.
    """

    id: int
    name: str | None = None
    season: int | None = None
    number: int | None = None
    type: str | None = None
    airdate: str | None = None
    runtime: int | None = None
    rating: TvmazeRating | None = None
    image: TvmazeImage | None = None
    summary: str | None = None
