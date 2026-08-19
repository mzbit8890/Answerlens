import asyncio

import pytest

import graph.workflow as workflow
from providers.search import RawSearchResult, SearchRequestError
from schemas.agentic import (
    AgenticAuditTimeoutError,
    EvidenceGap,
    EvidenceGapSet,
    GeoExperiment,
    GeoExperimentSet,
    TargetedResearchPlan,
    TargetedResearchPlanSet,
)
from schemas.brand import BrandProfile
from schemas.crawl import CrawledPage, CrawlResult, CrawlStatus
from schemas.evidence import ClaimEvidenceMap, ConfidenceLevel
from schemas.machine_readable import (
    LlmsTxtInspection,
    MachineReadableAudit,
    MachineReadableSummary,
    ParseStatus,
    RobotsInspection,
    SitemapInspection,
    StructuredDataInspection,
    SurfaceStatus,
)
from schemas.query import (
    EvaluationStatus,
    GroundedExternalEvidence,
    QueryEvaluation,
    QueryIntent,
    ReadinessLevel,
    RecommendationQuery,
    RecommendationQuerySet,
    SourceOwnership,
)


QUERY = "Best project tools for engineering teams"


def crawl_fixture():
    return CrawlResult(
        target_url="https://example.com/",
        pages=[
            CrawledPage(
                requested_url="https://example.com/",
                final_url="https://example.com/",
                status=CrawlStatus.SUCCESS,
                title="Example",
                content="Example builds project tools.",
            )
        ],
    )


def audit_fixture():
    structured = StructuredDataInspection(status=SurfaceStatus.MISSING)
    return MachineReadableAudit(
        target_url="https://example.com/",
        robots=RobotsInspection(
            source_url="https://example.com/robots.txt",
            status=SurfaceStatus.MISSING,
            parse_status=ParseStatus.NOT_APPLICABLE,
        ),
        sitemap=SitemapInspection(status=SurfaceStatus.MISSING),
        llms_txt=LlmsTxtInspection(
            source_url="https://example.com/llms.txt", status=SurfaceStatus.MISSING
        ),
        structured_data=structured,
        summary=MachineReadableSummary(
            robots_status=SurfaceStatus.MISSING,
            sitemap_status=SurfaceStatus.MISSING,
            sitemap_urls_discovered=0,
            llms_txt_status=SurfaceStatus.MISSING,
            llms_txt_links_discovered=0,
            structured_data_status=SurfaceStatus.MISSING,
            structured_data_pages=0,
        ),
    )


def external_evidence(url, excerpt):
    return GroundedExternalEvidence(
        url=url, excerpt=excerpt, source_ownership=SourceOwnership.INDEPENDENT
    )


class FakeValidator:
    async def validate(self, url, **kwargs):
        return "https://example.com/"


class FakeSearch:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    async def search(self, query, *, max_results):
        self.calls.append(query)
        if self.fail:
            raise SearchRequestError("search unavailable")
        if query == QUERY:
            return [
                RawSearchResult(
                    url="https://review.test/original",
                    title="Original review",
                    content="Example has limited project evidence.",
                    score=0.4,
                )
            ]
        round_number = len([call for call in self.calls if call != QUERY])
        return [
            RawSearchResult(
                url=f"https://research.test/round-{round_number}",
                title=f"Research round {round_number}",
                content=f"Example has strong engineering evidence round {round_number}.",
                score=0.9,
            )
        ]


class WorkflowProvider:
    def __init__(self, mode="high", fail_brand=False):
        self.mode = mode
        self.fail_brand = fail_brand
        self.evaluation_calls = 0
        self.plan_calls = 0
        self.response_models = []

    async def generate_structured(self, prompt, response_model):
        self.response_models.append(response_model.__name__)
        if response_model is BrandProfile:
            if self.fail_brand:
                raise RuntimeError("brand provider failure")
            return BrandProfile(brand="Example", category="Project software")
        if response_model is RecommendationQuerySet:
            return RecommendationQuerySet(
                queries=[
                    RecommendationQuery(
                        query=QUERY,
                        intent=QueryIntent.CATEGORY_DISCOVERY,
                        rationale="The profile identifies project software.",
                    )
                ]
            )
        if response_model is QueryEvaluation:
            self.evaluation_calls += 1
            if self.mode == "high" or (self.mode == "one_round" and self.evaluation_calls > 1):
                if self.evaluation_calls == 1:
                    url = "https://review.test/original"
                    excerpt = "Example has limited project evidence."
                else:
                    url = "https://research.test/round-1"
                    excerpt = "Example has strong engineering evidence round 1."
                return QueryEvaluation(
                    query=QUERY,
                    status=EvaluationStatus.COMPLETED,
                    readiness=ReadinessLevel.HIGH,
                    supporting_evidence=[external_evidence(url, excerpt)],
                    confidence=ConfidenceLevel.HIGH,
                    reason="Retrieved evidence directly supports the query.",
                )
            return QueryEvaluation(
                query=QUERY,
                status=EvaluationStatus.COMPLETED,
                readiness=ReadinessLevel.LOW,
                missing_evidence=["More independent evidence is needed."],
                confidence=ConfidenceLevel.LOW,
                reason="Current evidence is insufficient for confidence.",
            )
        if response_model is TargetedResearchPlanSet:
            self.plan_calls += 1
            return TargetedResearchPlanSet(
                plans=[
                    TargetedResearchPlan(
                        original_query=QUERY,
                        search_query=f"Example engineering evidence round {self.plan_calls}",
                        reason="Resolve missing independent evidence.",
                    )
                ]
            )
        if response_model is EvidenceGapSet:
            return EvidenceGapSet(
                gaps=[
                    EvidenceGap(
                        query=QUERY,
                        readiness=ReadinessLevel.LOW,
                        why="Evidence remains insufficient.",
                        missing_evidence=["More independent evidence is needed."],
                        confidence=ConfidenceLevel.LOW,
                    )
                ]
            )
        if response_model is GeoExperimentSet:
            return GeoExperimentSet(
                experiments=[
                    GeoExperiment(
                        observation="The query remains low readiness.",
                        hypothesis="Explicit evidence may improve readiness.",
                        proposed_change="Publish a specific engineering workflow evidence page.",
                        evaluation_queries=[QUERY],
                        success_condition="Readiness reaches medium or high on rerun.",
                        confidence=ConfidenceLevel.MEDIUM,
                    )
                ]
            )
        raise AssertionError(f"Unexpected model {response_model}")


def patch_network_stages(monkeypatch, *, slow=False):
    monkeypatch.setattr(workflow, "URLSafetyValidator", FakeValidator)

    async def fake_crawl(url):
        if slow:
            await asyncio.sleep(1)
        return crawl_fixture()

    async def fake_inspect(url, crawl_result):
        return audit_fixture()

    monkeypatch.setattr(workflow, "crawl_website", fake_crawl)
    monkeypatch.setattr(workflow, "inspect_machine_readable_surfaces", fake_inspect)


def run(monkeypatch, provider, search=None):
    patch_network_stages(monkeypatch)
    return asyncio.run(
        workflow.run_agentic_audit(
            "https://example.com",
            structured_provider=provider,
            search_provider=search or FakeSearch(),
        )
    )


def test_successful_graph_reaches_completion_in_logical_order(monkeypatch):
    result = run(monkeypatch, WorkflowProvider("high"))
    stages = [event.stage for event in result.execution_trace]
    assert stages == [
        "validate_target",
        "crawl_evidence",
        "inspect_machine_readable_surfaces",
        "extract_brand_profile",
        "build_claim_evidence_map",
        "generate_recommendation_queries",
        "retrieve_external_evidence",
        "run_grounded_query_evaluations",
        "diagnose_evidence_gaps",
        "generate_geo_experiments",
        "calculate_metrics",
        "audit_complete",
    ]
    assert result.research_rounds == []
    assert result.metrics.strong_queries == 1
    assert result.execution_trace[1].counters == {
        "pages_returned": 1,
        "pages_successful": 1,
    }
    trace_text = " ".join(event.model_dump_json() for event in result.execution_trace)
    assert "GEMINI_API_KEY" not in trace_text
    assert "BEGIN UNTRUSTED" not in trace_text


def test_low_confidence_enters_research_then_acceptable_confidence_exits(monkeypatch):
    provider = WorkflowProvider("one_round")
    result = run(monkeypatch, provider)
    assert len(result.research_rounds) == 1
    assert provider.evaluation_calls == 2
    assert result.query_evaluations.evaluations[0].confidence is ConfidenceLevel.HIGH
    assert any(event.status.value == "retrying" for event in result.execution_trace)


def test_low_confidence_graph_stops_after_two_rounds(monkeypatch):
    provider = WorkflowProvider("always_low")
    result = run(monkeypatch, provider)
    assert len(result.research_rounds) == 2
    assert provider.evaluation_calls == 3
    assert len(result.evidence_gaps.gaps) == 1
    assert len(result.experiments.experiments) == 1


def test_unavailable_evaluation_does_not_enter_research(monkeypatch):
    provider = WorkflowProvider("high")
    result = run(monkeypatch, provider, FakeSearch(fail=True))
    assert result.query_evaluations.evaluations[0].status is EvaluationStatus.UNAVAILABLE
    assert result.research_rounds == []
    assert provider.evaluation_calls == 0
    assert result.metrics.unavailable_evaluations == 1


def test_critical_provider_failure_propagates_without_fabricated_result(monkeypatch):
    patch_network_stages(monkeypatch)
    with pytest.raises(RuntimeError, match="brand provider failure"):
        asyncio.run(
            workflow.run_agentic_audit(
                "https://example.com",
                structured_provider=WorkflowProvider(fail_brand=True),
                search_provider=FakeSearch(),
            )
        )


def test_global_timeout_is_enforced(monkeypatch):
    patch_network_stages(monkeypatch, slow=True)
    monkeypatch.setattr(workflow, "AUDIT_TIMEOUT", 0.01)
    with pytest.raises(AgenticAuditTimeoutError, match="deadline"):
        asyncio.run(
            workflow.run_agentic_audit(
                "https://example.com",
                structured_provider=WorkflowProvider(),
                search_provider=FakeSearch(),
            )
        )


def test_graph_contains_real_conditional_research_edges():
    graph = workflow.build_agentic_audit_graph(WorkflowProvider(), FakeSearch())
    drawable = graph.get_graph()
    edges = {(edge.source, edge.target, edge.conditional) for edge in drawable.edges}
    assert ("run_grounded_query_evaluations", "plan_targeted_research", True) in edges
    assert ("re_evaluate_changed_queries", "plan_targeted_research", True) in edges
