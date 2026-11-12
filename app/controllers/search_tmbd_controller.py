"""Search endpoint for The Movie Database (TMDB)."""

from fastapi import APIRouter, Depends

from app.api.deps import SearchParams, get_search_params, make_provider_getter
from app.models.domain.search_result import SearchResult
from app.providers.base import BaseProvider

router = APIRouter(
    prefix="/search/tmdb",
    tags=["Search: The Movie Database (TMDB)"],
)

get_tmdb = make_provider_getter("tmdb")


@router.get(
    "",
    response_model=list[SearchResult],
    summary="Search TMDB by title",
    response_description="Matching movies and TV series from TMDB.",
)
async def search_tmdb(
    params: SearchParams = Depends(get_search_params),
    provider: BaseProvider = Depends(get_tmdb),
) -> list[SearchResult]:
    """Search **The Movie Database (TMDB)** for movies and TV series by title."""
    return await provider.search(params.title, year=params.year, media_type=params.media_type)
