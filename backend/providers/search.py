from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RawSearchResult:
    url: str
    title: str
    content: str
    score: float | None = None


class SearchProvider(Protocol):
    async def search(self, query: str, *, max_results: int) -> list[RawSearchResult]:
        """Return transport-level search results without fetching result URLs."""
        ...


class SearchProviderError(RuntimeError):
    """Base external-search provider failure."""


class SearchConfigurationError(SearchProviderError):
    """The real search provider cannot be configured."""


class SearchRequestError(SearchProviderError):
    """An external search request failed."""
