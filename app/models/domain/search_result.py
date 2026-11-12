"""Lightweight summary model for search hits.

A title search returns many candidates, and the caller only needs enough to
tell them apart and choose one. ``SearchResult`` carries that summary. The full
record (plot, genres, rating and so on) comes from a second call to
``get_details()``, which returns a ``Media`` object from ``media.py``.

Flow:
    search() -> list[SearchResult] -> caller picks one -> get_details(source_id)
"""

from pydantic import BaseModel

from app.models.domain.media import MediaType


class SearchResult(BaseModel):
    """One candidate match from a provider's title search.

    This is a summary, not a full record. It deliberately omits plot, genres
    and rating because search endpoints rarely return them, and the full
    ``Media`` models would be mostly empty here.

    Attributes:
        source: Name of the provider that returned this hit, e.g. ``"tmdb"``.
        source_id: The provider's own ID, in the form ``get_details()``
            accepts. Only unique within ``source``. TMDB IDs carry a kind
            prefix (``movie:27205``, ``tv:1396``) because movies and shows
            share number ranges.
        imdb_id: IMDb ID if the provider supplies one in search results.
            ``None`` is common (TMDB search does not include it), so do not
            treat it as "has no IMDb entry". It is filled in by
            ``get_details()``.
        media_type: Movie or series. Search does not return episodes. Anime
            appears under its normal format; see ``is_anime``.
        title: Display title as reported by the provider.
        year: Release or first-air year. ``None`` for unreleased or undated
            titles.
        poster_url: Absolute URL of a poster image, or ``None``.
        is_anime: ``True`` or ``False`` when a mapper is confident, ``None``
            when unknown. ``None`` is not the same as ``False``. Use it to
            label or filter results, not as a guarantee.
    """

    source: str
    source_id: str
    imdb_id: str | None = None
    media_type: MediaType
    title: str
    year: int | None = None
    poster_url: str | None = None
    is_anime: bool | None = None
