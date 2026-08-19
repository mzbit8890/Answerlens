import asyncio

import pytest

from agents.research_agent import (
    TargetedResearchError,
    merge_targeted_research,
    plan_targeted_research,
    research_candidates,
)
from providers.search import RawSearchResult
from schemas.agentic import TargetedResearchPlan, TargetedResearchPlanSet
from schemas.brand import BrandProfile
from schemas.evidence import ConfidenceLevel
from schemas.query import (
    EvaluationStatus,
    QueryEvaluation,
    QueryIntent,
    ReadinessLevel,
    RecommendationQuery,
)
from schemas.research import (
    ExternalResearchBatch,
    ExternalSearchResult,
    QueryResearchResult,
    ResearchStatus,
)
from schemas.query import SourceOwnership


def evaluation(query="Original", confidence=ConfidenceLevel.LOW, status=EvaluationStatus.COMPLETED):
    return QueryEvaluation(
        query=query,
        status=status,
        readiness=ReadinessLevel.LOW if status is EvaluationStatus.COMPLETED else None,
        confidence=confidence if status is EvaluationStatus.COMPLETED else None,
        reason="More evidence is needed." if status is EvaluationStatus.COMPLETED else "Unavailable.",
        missing_evidence=["Independent support"] if status is EvaluationStatus.COMPLETED else [],
    )


class PlannerProvider:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def generate_structured(self, prompt, response_model):
        self.calls.append((prompt, response_model))
        return self.responses.pop(0)


def plan(original="Original", search="Targeted search"):
    return TargetedResearchPlan(
        original_query=original, search_query=search, reason="Find independent evidence."
    )


def result(url, score):
    return ExternalSearchResult(
        url=url,
        domain=url.split("/")[2],
        title="Source",
        content="Evidence",
        source_ownership=SourceOwnership.INDEPENDENT,
        relevance_score=score,
    )


def research(query_text, results, status=ResearchStatus.COMPLETED, error=None):
    return QueryResearchResult(
        query=RecommendationQuery(
            query=query_text, intent=QueryIntent.PROBLEM_DRIVEN, rationale="Research"
        ),
        status=status,
        results=results,
        error=error,
    )


def test_only_completed_low_confidence_evaluations_are_candidates():
    candidates = research_candidates(
        [
            evaluation("low"),
            evaluation("medium", ConfidenceLevel.MEDIUM),
            evaluation("unavailable", status=EvaluationStatus.UNAVAILABLE),
        ]
    )
    assert [item.query for item in candidates] == ["low"]


def test_planner_preserves_exact_candidates_and_retries_semantic_error():
    invalid = TargetedResearchPlanSet(plans=[plan("Invented")])
    valid = TargetedResearchPlanSet(plans=[plan()])
    provider = PlannerProvider(invalid, valid)
    output = asyncio.run(
        plan_targeted_research(BrandProfile(brand="Example"), [evaluation()], provider)
    )
    assert output == valid
    assert len(provider.calls) == 2
    assert "UNTRUSTED DATA" in provider.calls[0][0]


def test_non_candidate_and_duplicate_plans_are_rejected():
    invalid = TargetedResearchPlanSet(plans=[plan("Other")])
    provider = PlannerProvider(invalid, invalid)
    with pytest.raises(TargetedResearchError):
        asyncio.run(
            plan_targeted_research(BrandProfile(brand="Example"), [evaluation()], provider)
        )
    with pytest.raises(ValueError):
        TargetedResearchPlanSet(plans=[plan(), plan(search="Different")])


def test_merge_deduplicates_scores_bounds_and_preserves_ownership():
    existing = [result(f"https://source{i}.test/page", 0.1 + i * 0.01) for i in range(5)]
    additional = [
        result("https://source0.test/page", 1.0),
        result("https://best.test/page", 0.99),
        result("https://second.test/page", 0.98),
    ]
    current = ExternalResearchBatch(query_results=[research("Original", existing)])
    targeted = ExternalResearchBatch(query_results=[research("Targeted search", additional)])
    merged, changed = merge_targeted_research(
        current, TargetedResearchPlanSet(plans=[plan()]), targeted
    )
    urls = [item.url for item in merged.query_results[0].results]
    assert len(urls) == 5
    assert urls[:2] == ["https://best.test/page", "https://second.test/page"]
    assert len(urls) == len(set(urls))
    assert all(item.source_ownership is SourceOwnership.INDEPENDENT for item in merged.query_results[0].results)
    assert changed == {"Original"}


def test_failed_targeted_search_is_explicit_and_does_not_change_catalog():
    current = ExternalResearchBatch(
        query_results=[research("Original", [result("https://source.test/page", 0.5)])]
    )
    failed = ExternalResearchBatch(
        query_results=[
            research("Targeted search", [], ResearchStatus.FAILED, "SearchRequestError")
        ]
    )
    merged, changed = merge_targeted_research(
        current, TargetedResearchPlanSet(plans=[plan()]), failed
    )
    assert merged == current
    assert changed == set()
