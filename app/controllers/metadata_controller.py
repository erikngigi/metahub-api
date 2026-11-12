"""Metadata endpoint: full details for one item from one provider."""

from fastapi import APIRouter, Depends

from app.api.deps import get_provider
from app.models.domain.media import Media
from app.providers.base import BaseProvider
from app.validators.common import validate_provider_id

router = APIRouter(tags=["metadata"])


@router.get("/metadata/{provider}/{provider_id}", response_model=Media)
async def get_metadata(
    provider_id: str,
    selected: BaseProvider = Depends(get_provider),
) -> Media:
    """Return a Movie, Series or Episode for an ID taken from a search result."""
    return await selected.get_details(validate_provider_id(provider_id))
