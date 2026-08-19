import os
from typing import Any

from tavily import AsyncTavilyClient

from providers.search import (
    RawSearchResult,
    SearchConfigurationError,
    SearchRequestError,
)
from schemas.research import MAX_RESULTS_PER_QUERY


class TavilySearchProvider:
    def __init__(self, *, client: Any | None = None) -> None:
        if client is not None:
            self._client = client
            return

        api_key = os.getenv("TAVILY_API_KEY")

        if not api_key:
            raise SearchConfigurationError(
                "TAVILY_API_KEY is required to construct the Tavily provider"
            )

        try:
            self._client = AsyncTavilyClient(api_key=api_key)
        except Exception as exc:
            raise SearchConfigurationError(
                "Tavily client configuration failed"
            ) from exc

    async def search(
        self,
        query: str,
        *,
        max_results: int,
    ) -> list[RawSearchResult]:
        bounded_results = min(
            max(max_results, 1),
            MAX_RESULTS_PER_QUERY,
        )

        try:
            response = await self._client.search(
                query=query,
                topic="general",
                search_depth="basic",
                max_results=bounded_results,
                include_answer=False,
                include_raw_content=False,
                auto_parameters=False,
            )
        except Exception as exc:
            raise SearchRequestError(
                "Tavily search request failed"
            ) from exc

        if not isinstance(response, dict):
            raise SearchRequestError(
                "Tavily search returned an invalid response"
            )

        raw_results = response.get("results")

        if not isinstance(raw_results, list):
            raise SearchRequestError(
                "Tavily search returned an invalid results payload"
            )

        results: list[RawSearchResult] = []

        for item in raw_results:
            if not isinstance(item, dict):
                continue

            url = item.get("url")
            title = item.get("title")
            content = item.get("content")
            score = item.get("score")

            if not all(
                isinstance(value, str)
                for value in (url, title, content)
            ):
                continue

            results.append(
                RawSearchResult(
                    url=url,
                    title=title,
                    content=content,
                    score=(
                        score
                        if isinstance(score, (int, float))
                        else None
                    ),
                )
            )

        return results[:bounded_results]