"""Abstract base contract for metadata provider adapters."""

from abc import ABC, abstractmethod
from typing import ClassVar

from app.models.domain.media import Media, MediaType
from app.models.domain.search_result import SearchResult


class BaseProvider(ABC):
    """Contract every provider adapter implements."""

    name: ClassVar[str]

    @property
    def is_configured(self) -> bool:
        """False when credentials are missing; the registry can skip the provider."""
        return True

    @abstractmethod
    async def search(
        self,
        title: str,
        *,
        year: int | None = None,
        media_type: MediaType | None = None,
    ) -> list[SearchResult]:
        """Search for matching titles from the provider."""

    ...

    @abstractmethod
    async def get_details(self, provider_id: str) -> Media:
        """Fetch full media details for a provider-specific identifier."""

    ...
