from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query, Request

from app.core.http_client import HttpClient
from app.exceptions.errors import ProviderNotFound
from app.models.domain.media import MediaType
from app.providers.base import BaseProvider
from app.validators.common import MAX_QUERY_LENGTH, sanitize_query, validate_year

# ---------- Shared resources (created once in main.py's lifespan) ----------


def get_http_client(request: Request) -> HttpClient:
    return request.app.state.http_client


def get_providers(request: Request) -> list[BaseProvider]:
    return request.app.state.providers


# ---------- Validated query parameters ----------


@dataclass(frozen=True)
class SearchParams:
    title: str
    year: int | None
    media_type: MediaType | None


def get_search_params(
    title: Annotated[str, Query(min_length=1, max_length=MAX_QUERY_LENGTH)],
    year: Annotated[int | None, Query()] = None,
    media_type: Annotated[MediaType | None, Query()] = None,
) -> SearchParams:
    """Dependency for search endpoints. FastAPI checks types and length;
    the validators then sanitise and enforce range rules."""
    return SearchParams(
        title=sanitize_query(title),
        year=validate_year(year),
        media_type=media_type,
    )


def get_provider(provider: str, providers: list[BaseProvider] = Depends(get_providers)) -> BaseProvider:
    """Look up a registered provider by its name (the ``{provider}`` path parameter).

    Raises:
        ProviderNotFound: If no provider with that name is registered.
    """
    for candidate in providers:
        if candidate.name == provider.strip().lower():
            return candidate
    raise ProviderNotFound(provider, "unknown provider")


def make_provider_getter(name: str):
    """Build a dependency that returns the registered provider called ``name``.

    Raises:
        ProviderNotFound: If that provider isn't registered.
    """

    def _get(providers: list[BaseProvider] = Depends(get_providers)) -> BaseProvider:
        for p in providers:
            if p.name == name:
                return p
        raise ProviderNotFound(name, "provider is not registered")

    return _get
