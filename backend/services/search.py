import asyncio
from urllib.parse import urlsplit

from guardrails.url_safety import (
    URLSafetyError,
    company_scope,
    is_within_scope,
    validate_url_reference,
)
from providers.search import (
    SearchProvider,
    SearchProviderError,
)
from schemas.query import (
    RecommendationQuerySet,
    SourceOwnership,
)
from schemas.research import (
    MAX_RESULT_CONTENT_LENGTH,
    MAX_RESULT_TITLE_LENGTH,
    MAX_RESULTS_PER_QUERY,
    ExternalResearchBatch,
    ExternalSearchResult,
    QueryResearchResult,
    ResearchStatus,
)

MAX_CONCURRENT_SEARCHES = 3


def _validated_results(
    raw_results: list,
    target_scope: str,
) -> tuple[list[ExternalSearchResult], int]:
    results: list[ExternalSearchResult] = []
    seen: set[str] = set()
    discarded = 0

    for raw in raw_results:
        try:
            url = validate_url_reference(raw.url)
        except (AttributeError, URLSafetyError):
            discarded += 1
            continue

        title = raw.title.strip()[:MAX_RESULT_TITLE_LENGTH]
        content = raw.content.strip()[:MAX_RESULT_CONTENT_LENGTH]

        if not title or not content or url in seen:
            discarded += 1
            continue

        if len(results) >= MAX_RESULTS_PER_QUERY:
            discarded += 1
            continue

        hostname = urlsplit(url).hostname
        assert hostname is not None

        score = raw.score

        if (
            not isinstance(score, (int, float))
            or not 0 <= score <= 1
        ):
            score = None

        seen.add(url)

        results.append(
            ExternalSearchResult(
                url=url,
                domain=hostname,
                title=title,
                content=content,
                source_ownership=(
                    SourceOwnership.BRAND_OWNED
                    if is_within_scope(
                        hostname,
                        target_scope,
                    )
                    else SourceOwnership.INDEPENDENT
                ),
                relevance_score=score,
            )
        )

    return results, discarded


async def research_queries(
    query_set: RecommendationQuerySet,
    target_url: str,
    search_provider: SearchProvider,
) -> ExternalResearchBatch:
    normalized_target = validate_url_reference(target_url)

    target_host = urlsplit(normalized_target).hostname
    assert target_host is not None

    target_scope = company_scope(target_host)

    semaphore = asyncio.Semaphore(
        MAX_CONCURRENT_SEARCHES
    )

    async def research_one(
        index: int,
    ) -> tuple[int, QueryResearchResult]:
        query = query_set.queries[index]

        try:
            async with semaphore:
                raw_results = await search_provider.search(
                    query.query,
                    max_results=MAX_RESULTS_PER_QUERY,
                )

            results, discarded = _validated_results(
                raw_results,
                target_scope,
            )

            outcome = QueryResearchResult(
                query=query,
                status=ResearchStatus.COMPLETED,
                results=results,
                discarded_results=discarded,
            )

        except SearchProviderError as exc:
            outcome = QueryResearchResult(
                query=query,
                status=ResearchStatus.FAILED,
                error=(
                    "external search failed: "
                    f"{type(exc).__name__}"
                ),
            )

        return index, outcome

    indexed = await asyncio.gather(
        *(
            research_one(index)
            for index in range(len(query_set.queries))
        )
    )

    indexed.sort(
        key=lambda item: item[0]
    )

    return ExternalResearchBatch(
        query_results=[
            item[1]
            for item in indexed
        ]
    )