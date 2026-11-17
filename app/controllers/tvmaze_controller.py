"""All TVMaze endpoints: search, seasons and episode lists, in one router."""

from fastapi import APIRouter, Depends

from app.api.deps import SearchParams, get_search_params, make_provider_getter
from app.models.domain.search_result import SearchResult
from app.models.domain.season import SeasonEpisodesResponse, SeasonsResponse
from app.providers.tvmaze_provider import TvmazeProvider
from app.validators.common import validate_provider_id

router = APIRouter(
    prefix="/tvmaze",
    tags=["TVMaze"],
    responses={
        401: {"description": "Missing or invalid client key."},
        502: {"description": "TVMaze returned an unusable response."},
        504: {"description": "TVMaze did not respond in time."},
    },
)

get_tvmaze = make_provider_getter("tvmaze")


@router.get(
    "/search",
    response_model=list[SearchResult],
    summary="1. Search TV series by title",
    responses={422: {"description": "Invalid `title` or `year`."}},
)
async def search_shows(
    params: SearchParams = Depends(get_search_params),
    provider: TvmazeProvider = Depends(get_tvmaze),
) -> list[SearchResult]:
    """Search **TVMaze** for TV series by title.

    Copy a result's `source_id` (for example `show:674`) into the seasons route.
    The `year` filter is applied after TVMaze responds.
    """
    return await provider.search(params.title, year=params.year)


@router.get(
    "/shows/{show_id}/seasons",
    response_model=SeasonsResponse,
    summary="2. Get a show and its seasons",
    responses={404: {"description": "Malformed ID, or TVMaze has no such show."}},
)
async def get_show_seasons(
    show_id: str,
    provider: TvmazeProvider = Depends(get_tvmaze),
) -> SeasonsResponse:
    """Return a show's details and all of its seasons.

    Copy a season's `source_id` (for example `season:2696`) into the episodes
    route. That ID is TVMaze's own, not the season number.
    """
    return await provider.get_seasons(validate_provider_id(show_id))


@router.get(
    "/seasons/{season_id}/episodes",
    response_model=SeasonEpisodesResponse,
    summary="3. List the episodes of a season",
    responses={404: {"description": "Malformed ID, or TVMaze has no such season."}},
)
async def get_season_episodes(
    season_id: str,
    provider: TvmazeProvider = Depends(get_tvmaze),
) -> SeasonEpisodesResponse:
    """Return episode names with number, air date and runtime.

    Specials can have a `null` number and a `type` other than `regular`.
    Data from TVMaze is licensed CC BY-SA; credit TVMaze where you display it.
    """
    return await provider.get_season_episodes(validate_provider_id(season_id))
