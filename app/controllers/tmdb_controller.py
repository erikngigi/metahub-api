"""All TMDB endpoints: search, movies and TV shows, in one router."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.api.deps import SearchParams, get_search_params, make_provider_getter
from app.models.domain.media import Episode, Movie, Series
from app.models.domain.search_result import SearchResult
from app.models.domain.season import EpisodeLabel, SeasonDetailsResponse
from app.providers.tmdb_provider import TmdbProvider

router = APIRouter(
    prefix="/tmdb",
    tags=["TMDB"],
    responses={
        401: {"description": "Missing or invalid client key."},
        404: {"description": "TMDB has no such item."},
        502: {"description": "TMDB rejected our credentials or returned an unusable response."},
        504: {"description": "TMDB did not respond in time."},
    },
)

get_tmdb = make_provider_getter("tmdb")

MovieId = Annotated[
    int, Path(gt=0, description="TMDB movie ID, the number after `movie:` in a search result.", examples=[27205])
]
ShowId = Annotated[
    int, Path(gt=0, description="TMDB show ID, the number after `tv:` in a search result.", examples=[1396])
]
SeasonNumber = Annotated[
    int, Path(ge=0, le=100, description="Season number as used in filenames. `0` is specials.", examples=[1])
]
EpisodeNumber = Annotated[int, Path(ge=1, le=9999, description="Episode number within the season.", examples=[1])]


# ---------- Search ----------


@router.get(
    "/search",
    response_model=list[SearchResult],
    summary="Search movies and TV shows by title",
    responses={422: {"description": "Invalid `title`, `year` or `media_type`."}},
)
async def search_tmdb(
    params: SearchParams = Depends(get_search_params),
    provider: TmdbProvider = Depends(get_tmdb),
) -> list[SearchResult]:
    """Search **TMDB** by title.

    Each result's `source_id` shows where to go next:
    - `movie:27205` → `/tmdb/movies/27205`
    - `tv:1396` → `/tmdb/shows/1396`

    `imdb_id` is `null` here; it is only filled in by the details routes.
    """
    return await provider.search(params.title, year=params.year, media_type=params.media_type)


# ---------- Movies ----------


@router.get(
    "/movies/{movie_id}",
    response_model=Movie,
    summary="Get a movie",
)
async def get_movie(
    movie_id: MovieId,
    provider: TmdbProvider = Depends(get_tmdb),
) -> Movie:
    """Return full details for one **movie**: plot, genres, rating, runtime, poster and IMDb ID."""
    return await provider.get_movie(movie_id)


# ---------- Shows ----------


@router.get(
    "/shows/{show_id}",
    response_model=Series,
    summary="Get a TV show",
)
async def get_show(
    show_id: ShowId,
    provider: TmdbProvider = Depends(get_tmdb),
) -> Series:
    """Return full details for one **TV show**: status, season and episode counts, poster and IMDb ID."""
    return await provider.get_show(show_id)


@router.get(
    "/shows/{show_id}/seasons/{season}",
    response_model=SeasonDetailsResponse,
    summary="Get one season of a TV show",
)
async def get_show_season(
    show_id: ShowId,
    season: SeasonNumber,
    provider: TmdbProvider = Depends(get_tmdb),
) -> SeasonDetailsResponse:
    """Return a **season** and the list of its episodes.

    Each episode has its number, title, air date, runtime and rating.
    `season=0` returns specials. This makes a single TMDB request.
    """
    return await provider.get_show_season(show_id, season)


@router.get(
    "/shows/{show_id}/seasons/{season}/labels",
    response_model=list[EpisodeLabel],
    summary="Formatted episode names for a season",
)
async def get_season_labels(
    show_id: ShowId,
    season: SeasonNumber,
    provider: TmdbProvider = Depends(get_tmdb),
) -> list[EpisodeLabel]:
    """Return `Show S01E01 - Episode` labels for every episode in a season.

    Characters that are illegal in filenames (`: / \\ ? * " < > |`) are removed.
    Episodes without a number are skipped.
    """
    return await provider.get_season_labels(show_id, season)
