import asyncio

import pytest
from pydantic import ValidationError

from providers.search import (
    RawSearchResult,
    SearchRequestError,
)
from schemas.query import (
    QueryIntent,
    RecommendationQuery,
    RecommendationQuerySet,
    SourceOwnership,
)
from schemas.research import (
    QueryResearchResult,
    ResearchStatus,
)
from services.search import (
    MAX_CONCURRENT_SEARCHES,
    research_queries,
)


def query(text):
    return RecommendationQuery(
        query=text,
        intent=QueryIntent.CATEGORY_DISCOVERY,
        rationale="Research",
    )


class FakeSearchProvider:
    def __init__(self, responses):
        self.responses = responses
        self.active = 0
        self.max_active = 0
        self.calls = []

    async def search(
        self,
        search_query,
        *,
        max_results,
    ):
        self.calls.append(
            (
                search_query,
                max_results,
            )
        )

        self.active += 1

        self.max_active = max(
            self.max_active,
            self.active,
        )

        await asyncio.sleep(0)

        self.active -= 1

        response = self.responses[
            search_query
        ]

        if isinstance(
            response,
            Exception,
        ):
            raise response

        return response


def raw(
    url,
    title="Example",
    content="Example content",
    score=0.5,
):
    return RawSearchResult(
        url=url,
        title=title,
        content=content,
        score=score,
    )


def test_validates_deduplicates_bounds_and_classifies_results():
    results = [
        raw(
            "https://example.com/product",
            content="Brand owned",
        ),
        raw(
            "https://EXAMPLE.com/product/",
            content="Duplicate",
        ),
        raw(
            "http://independent.test/review",
            content="Example independent review",
        ),
        raw(
            "ftp://bad.test/file"
        ),
        raw(
            "http://localhost/private"
        ),
        raw(
            "http://10.0.0.5/private"
        ),
        raw(
            "https://user:pass@example.net/private"
        ),
    ] + [
        raw(
            f"https://source{i}.test/page"
        )
        for i in range(10)
    ]

    provider = FakeSearchProvider(
        {
            "q": results,
        }
    )

    batch = asyncio.run(
        research_queries(
            RecommendationQuerySet(
                queries=[
                    query("q"),
                ]
            ),
            "https://example.com",
            provider,
        )
    )

    research = batch.query_results[0]

    assert (
        research.status
        is ResearchStatus.COMPLETED
    )

    assert len(
        research.results
    ) == 5

    assert (
        research.results[0].source_ownership
        is SourceOwnership.BRAND_OWNED
    )

    assert (
        research.results[1].source_ownership
        is SourceOwnership.INDEPENDENT
    )

    assert (
        research.results[1].domain
        == "independent.test"
    )

    assert (
        research.discarded_results
        == len(results) - 5
    )

    assert provider.calls == [
        (
            "q",
            5,
        )
    ]


def test_title_content_bounds_and_brand_name_does_not_change_ownership():
    provider = FakeSearchProvider(
        {
            "q": [
                raw(
                    "https://third-party.test",
                    title="t" * 1000,
                    content=(
                        "Example "
                        + "c" * 5000
                    ),
                )
            ]
        }
    )

    result = asyncio.run(
        research_queries(
            RecommendationQuerySet(
                queries=[
                    query("q"),
                ]
            ),
            "https://example.com",
            provider,
        )
    ).query_results[0].results[0]

    assert len(
        result.title
    ) == 500

    assert len(
        result.content
    ) == 4000

    assert (
        result.source_ownership
        is SourceOwnership.INDEPENDENT
    )


def test_batch_order_concurrency_zero_results_and_partial_failure():
    queries = RecommendationQuerySet(
        queries=[
            query(
                f"q{i}"
            )
            for i in range(12)
        ]
    )

    responses = {
        f"q{i}": []
        for i in range(12)
    }

    responses["q4"] = SearchRequestError(
        "failure"
    )

    provider = FakeSearchProvider(
        responses
    )

    batch = asyncio.run(
        research_queries(
            queries,
            "https://example.com",
            provider,
        )
    )

    assert [
        item.query.query
        for item in batch.query_results
    ] == [
        f"q{i}"
        for i in range(12)
    ]

    assert (
        provider.max_active
        <= MAX_CONCURRENT_SEARCHES
    )

    assert (
        batch.query_results[0].status
        is ResearchStatus.COMPLETED
    )

    assert (
        batch.query_results[0].results
        == []
    )

    assert (
        batch.query_results[4].status
        is ResearchStatus.FAILED
    )

    assert (
        batch.query_results[4].error
        and "SearchRequestError"
        in batch.query_results[4].error
    )


def test_unexpected_internal_failure_is_not_swallowed():
    provider = FakeSearchProvider(
        {
            "q": RuntimeError(
                "programming bug"
            )
        }
    )

    with pytest.raises(
        RuntimeError,
        match="programming bug",
    ):
        asyncio.run(
            research_queries(
                RecommendationQuerySet(
                    queries=[
                        query("q"),
                    ]
                ),
                "https://example.com",
                provider,
            )
        )


def test_research_status_rejects_contradictory_states():
    with pytest.raises(
        ValidationError
    ):
        QueryResearchResult(
            query=query("q"),
            status=ResearchStatus.FAILED,
        )

    with pytest.raises(
        ValidationError
    ):
        QueryResearchResult(
            query=query("q"),
            status=ResearchStatus.COMPLETED,
            error="not completed",
        )