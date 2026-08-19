import asyncio
from time import perf_counter
from typing import NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph

from agents.brand_agent import extract_brand_profile
from agents.evaluation_agent import evaluate_query, evaluate_research_batch
from agents.evidence_agent import build_claim_evidence_map
from agents.experiment_agent import generate_geo_experiments
from agents.gap_agent import diagnose_evidence_gaps
from agents.query_agent import generate_recommendation_queries
from agents.research_agent import (
    MAX_RESEARCH_RETRIES,
    merge_targeted_research,
    plan_targeted_research,
    research_candidates,
    retrieve_targeted_research,
)
from config import load_local_environment
from guardrails.url_safety import URLSafetyValidator
from providers.base import StructuredOutputProvider
from providers.gemini import GeminiStructuredOutputProvider
from providers.search import SearchProvider
from providers.tavily import TavilySearchProvider
from schemas.agentic import (
    AgentEvent,
    AgentEventStatus,
    AgenticAuditResult,
    AgenticAuditTimeoutError,
    AuditMetrics,
    EvidenceGapSet,
    GeoExperimentSet,
    ResearchRound,
    TargetedResearchPlanSet,
)
from schemas.brand import BrandProfile
from schemas.crawl import CrawlResult, CrawlStatus
from schemas.evidence import ClaimEvidenceMap, ClaimSupportStatus
from schemas.machine_readable import MachineReadableAudit
from schemas.query import QueryEvaluationSet, RecommendationQuerySet
from schemas.research import ExternalResearchBatch, ResearchStatus
from services.crawler import crawl_website
from services.machine_readable import inspect_machine_readable_surfaces
from services.metrics import calculate_audit_metrics
from services.search import research_queries

AUDIT_TIMEOUT = 120


class AuditState(TypedDict):
    target_url: str
    category: str | None
    known_competitors: list[str]
    execution_trace: list[AgentEvent]
    research_round: int
    research_rounds: list[ResearchRound]
    normalized_target_url: NotRequired[str]
    crawl_result: NotRequired[CrawlResult]
    machine_readable_audit: NotRequired[MachineReadableAudit]
    brand_profile: NotRequired[BrandProfile]
    claim_evidence_map: NotRequired[ClaimEvidenceMap]
    query_set: NotRequired[RecommendationQuerySet]
    external_research: NotRequired[ExternalResearchBatch]
    query_evaluations: NotRequired[QueryEvaluationSet]
    research_candidates: NotRequired[list]
    targeted_research_plans: NotRequired[TargetedResearchPlanSet]
    changed_queries: NotRequired[set[str]]
    research_blocked: NotRequired[bool]
    evidence_gaps: NotRequired[EvidenceGapSet]
    experiments: NotRequired[GeoExperimentSet]
    metrics: NotRequired[AuditMetrics]


def _duration_ms(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))


def _event(
    state: AuditState,
    stage: str,
    message: str,
    started: float,
    *,
    status: AgentEventStatus = AgentEventStatus.COMPLETED,
    counters: dict[str, int] | None = None,
) -> list[AgentEvent]:
    return [
        *state["execution_trace"],
        AgentEvent(
            stage=stage,
            status=status,
            message=message,
            duration_ms=_duration_ms(started),
            counters=counters or {},
        ),
    ]


def build_agentic_audit_graph(
    structured_provider: StructuredOutputProvider,
    search_provider: SearchProvider,
):
    async def validate_target(state: AuditState) -> dict:
        started = perf_counter()
        normalized = await URLSafetyValidator().validate(state["target_url"])
        return {
            "normalized_target_url": normalized,
            "execution_trace": _event(
                state, "validate_target", "Target website validated.", started
            ),
        }

    async def crawl_evidence(state: AuditState) -> dict:
        started = perf_counter()
        result = await crawl_website(state["normalized_target_url"])
        successful = sum(page.status is CrawlStatus.SUCCESS for page in result.pages)
        return {
            "crawl_result": result,
            "execution_trace": _event(
                state,
                "crawl_evidence",
                "Website evidence crawl completed.",
                started,
                counters={"pages_returned": len(result.pages), "pages_successful": successful},
            ),
        }

    async def inspect_surfaces(state: AuditState) -> dict:
        started = perf_counter()
        audit = await inspect_machine_readable_surfaces(
            state["normalized_target_url"], state["crawl_result"]
        )
        return {
            "machine_readable_audit": audit,
            "execution_trace": _event(
                state,
                "inspect_machine_readable_surfaces",
                "Machine-readable surfaces inspected.",
                started,
            ),
        }

    async def extract_profile(state: AuditState) -> dict:
        started = perf_counter()
        profile = await extract_brand_profile(
            state["crawl_result"],
            state["machine_readable_audit"],
            structured_provider,
            state["category"],
        )
        return {
            "brand_profile": profile,
            "execution_trace": _event(
                state,
                "extract_brand_profile",
                "Brand profile extracted.",
                started,
                counters={"claims": len(profile.claims)},
            ),
        }

    async def map_claims(state: AuditState) -> dict:
        started = perf_counter()
        mapping = await build_claim_evidence_map(
            state["brand_profile"],
            state["crawl_result"],
            state["machine_readable_audit"],
            structured_provider,
        )
        supported = sum(
            record.support_status is ClaimSupportStatus.SUPPORTED
            for record in mapping.records
        )
        return {
            "claim_evidence_map": mapping,
            "execution_trace": _event(
                state,
                "build_claim_evidence_map",
                "Candidate claims mapped to publisher evidence.",
                started,
                counters={"claims": len(mapping.records), "supported_claims": supported},
            ),
        }

    async def generate_queries(state: AuditState) -> dict:
        started = perf_counter()
        query_set = await generate_recommendation_queries(
            state["brand_profile"], structured_provider, state["known_competitors"]
        )
        return {
            "query_set": query_set,
            "execution_trace": _event(
                state,
                "generate_recommendation_queries",
                "Recommendation queries generated.",
                started,
                counters={"queries": len(query_set.queries)},
            ),
        }

    async def retrieve_external(state: AuditState) -> dict:
        started = perf_counter()
        research = await research_queries(
            state["query_set"], state["normalized_target_url"], search_provider
        )
        result_count = sum(len(item.results) for item in research.query_results)
        failures = sum(
            item.status is ResearchStatus.FAILED for item in research.query_results
        )
        return {
            "external_research": research,
            "execution_trace": _event(
                state,
                "retrieve_external_evidence",
                "External evidence retrieval completed.",
                started,
                counters={"results": result_count, "failed_queries": failures},
            ),
        }

    async def evaluate_queries(state: AuditState) -> dict:
        started = perf_counter()
        evaluations = await evaluate_research_batch(
            state["query_set"],
            state["brand_profile"],
            state["claim_evidence_map"],
            state["external_research"],
            structured_provider,
            state["known_competitors"],
        )
        candidates = research_candidates(evaluations.evaluations)
        return {
            "query_evaluations": evaluations,
            "research_candidates": candidates,
            "execution_trace": _event(
                state,
                "run_grounded_query_evaluations",
                "Grounded query evaluations completed.",
                started,
                counters={
                    "evaluations": len(evaluations.evaluations),
                    "research_candidates": len(candidates),
                },
            ),
        }

    def route_research(state: AuditState) -> str:
        if state.get("research_blocked"):
            return "diagnose_evidence_gaps"
        if state["research_round"] >= MAX_RESEARCH_RETRIES:
            return "diagnose_evidence_gaps"
        candidates = research_candidates(state["query_evaluations"].evaluations)
        return "plan_targeted_research" if candidates else "diagnose_evidence_gaps"

    async def plan_research(state: AuditState) -> dict:
        started = perf_counter()
        candidates = research_candidates(state["query_evaluations"].evaluations)
        plans = await plan_targeted_research(
            state["brand_profile"], candidates, structured_provider
        )
        return {
            "research_candidates": candidates,
            "targeted_research_plans": plans,
            "execution_trace": _event(
                state,
                "plan_targeted_research",
                "Targeted evidence research planned.",
                started,
                status=AgentEventStatus.RETRYING,
                counters={
                    "round": state["research_round"] + 1,
                    "plans": len(plans.plans),
                },
            ),
        }

    async def retrieve_more(state: AuditState) -> dict:
        started = perf_counter()
        targeted = await retrieve_targeted_research(
            state["targeted_research_plans"],
            state["normalized_target_url"],
            search_provider,
        )
        merged, changed = merge_targeted_research(
            state["external_research"], state["targeted_research_plans"], targeted
        )
        round_number = state["research_round"] + 1
        research_round = ResearchRound(
            round_number=round_number,
            plans=state["targeted_research_plans"],
            results=targeted.query_results,
        )
        failures = sum(
            item.status is ResearchStatus.FAILED for item in targeted.query_results
        )
        return {
            "external_research": merged,
            "changed_queries": changed,
            "research_round": round_number,
            "research_rounds": [*state["research_rounds"], research_round],
            "research_blocked": not changed,
            "execution_trace": _event(
                state,
                f"additional_research_round_{round_number}",
                "Additional evidence research completed.",
                started,
                status=AgentEventStatus.RETRYING,
                counters={
                    "round": round_number,
                    "changed_queries": len(changed),
                    "failed_searches": failures,
                },
            ),
        }

    async def re_evaluate(state: AuditState) -> dict:
        started = perf_counter()
        existing = {
            evaluation.query: evaluation
            for evaluation in state["query_evaluations"].evaluations
        }
        research_by_query = {
            item.query.query: item for item in state["external_research"].query_results
        }
        for query in state["query_set"].queries:
            if query.query in state["changed_queries"]:
                existing[query.query] = await evaluate_query(
                    query,
                    state["brand_profile"],
                    state["claim_evidence_map"],
                    research_by_query[query.query],
                    structured_provider,
                    state["known_competitors"],
                )
        evaluations = QueryEvaluationSet(
            evaluations=[existing[query.query] for query in state["query_set"].queries]
        )
        return {
            "query_evaluations": evaluations,
            "research_candidates": research_candidates(evaluations.evaluations),
            "execution_trace": _event(
                state,
                "re_evaluate_changed_queries",
                "Changed queries re-evaluated.",
                started,
                counters={"queries_re_evaluated": len(state["changed_queries"])},
            ),
        }

    async def diagnose_gaps(state: AuditState) -> dict:
        started = perf_counter()
        gaps = await diagnose_evidence_gaps(
            state["brand_profile"],
            state["query_evaluations"].evaluations,
            state["external_research"],
            structured_provider,
        )
        return {
            "evidence_gaps": gaps,
            "execution_trace": _event(
                state,
                "diagnose_evidence_gaps",
                "Evidence gaps diagnosed.",
                started,
                counters={"gaps": len(gaps.gaps)},
            ),
        }

    async def generate_experiments(state: AuditState) -> dict:
        started = perf_counter()
        experiments = await generate_geo_experiments(
            state["evidence_gaps"], state["query_set"], structured_provider
        )
        return {
            "experiments": experiments,
            "execution_trace": _event(
                state,
                "generate_geo_experiments",
                "Measurable GEO experiments generated.",
                started,
                counters={"experiments": len(experiments.experiments)},
            ),
        }

    async def calculate_metrics(state: AuditState) -> dict:
        started = perf_counter()
        metrics = calculate_audit_metrics(
            state["claim_evidence_map"],
            state["query_evaluations"],
            state["evidence_gaps"],
        )
        return {
            "metrics": metrics,
            "execution_trace": _event(
                state,
                "calculate_metrics",
                "Deterministic audit metrics calculated.",
                started,
                counters={
                    "completed_evaluations": metrics.completed_evaluations,
                    "unavailable_evaluations": metrics.unavailable_evaluations,
                },
            ),
        }

    async def complete_trace(state: AuditState) -> dict:
        started = perf_counter()
        return {
            "execution_trace": _event(
                state,
                "audit_complete",
                "Agentic evidence audit completed.",
                started,
                counters={"research_rounds": state["research_round"]},
            )
        }

    graph = StateGraph(AuditState)
    graph.add_node("validate_target", validate_target)
    graph.add_node("crawl_evidence", crawl_evidence)
    graph.add_node("inspect_machine_readable_surfaces", inspect_surfaces)
    graph.add_node("extract_brand_profile", extract_profile)
    graph.add_node("build_claim_evidence_map", map_claims)
    graph.add_node("generate_recommendation_queries", generate_queries)
    graph.add_node("retrieve_external_evidence", retrieve_external)
    graph.add_node("run_grounded_query_evaluations", evaluate_queries)
    graph.add_node("plan_targeted_research", plan_research)
    graph.add_node("retrieve_more_evidence", retrieve_more)
    graph.add_node("re_evaluate_changed_queries", re_evaluate)
    graph.add_node("diagnose_evidence_gaps", diagnose_gaps)
    graph.add_node("generate_geo_experiments", generate_experiments)
    graph.add_node("calculate_metrics", calculate_metrics)
    graph.add_node("complete_execution_trace", complete_trace)

    graph.add_edge(START, "validate_target")
    graph.add_edge("validate_target", "crawl_evidence")
    graph.add_edge("crawl_evidence", "inspect_machine_readable_surfaces")
    graph.add_edge("inspect_machine_readable_surfaces", "extract_brand_profile")
    graph.add_edge("extract_brand_profile", "build_claim_evidence_map")
    graph.add_edge("build_claim_evidence_map", "generate_recommendation_queries")
    graph.add_edge("generate_recommendation_queries", "retrieve_external_evidence")
    graph.add_edge("retrieve_external_evidence", "run_grounded_query_evaluations")
    graph.add_conditional_edges(
        "run_grounded_query_evaluations",
        route_research,
        {
            "plan_targeted_research": "plan_targeted_research",
            "diagnose_evidence_gaps": "diagnose_evidence_gaps",
        },
    )
    graph.add_edge("plan_targeted_research", "retrieve_more_evidence")
    graph.add_edge("retrieve_more_evidence", "re_evaluate_changed_queries")
    graph.add_conditional_edges(
        "re_evaluate_changed_queries",
        route_research,
        {
            "plan_targeted_research": "plan_targeted_research",
            "diagnose_evidence_gaps": "diagnose_evidence_gaps",
        },
    )
    graph.add_edge("diagnose_evidence_gaps", "generate_geo_experiments")
    graph.add_edge("generate_geo_experiments", "calculate_metrics")
    graph.add_edge("calculate_metrics", "complete_execution_trace")
    graph.add_edge("complete_execution_trace", END)
    return graph.compile()


async def run_agentic_audit(
    target_url: str,
    category: str | None = None,
    known_competitors: list[str] | None = None,
    structured_provider: StructuredOutputProvider | None = None,
    search_provider: SearchProvider | None = None,
) -> AgenticAuditResult:
    load_local_environment()
    llm = structured_provider or GeminiStructuredOutputProvider()
    search = search_provider or TavilySearchProvider()
    graph = build_agentic_audit_graph(llm, search)
    initial: AuditState = {
        "target_url": target_url,
        "category": category,
        "known_competitors": known_competitors or [],
        "execution_trace": [],
        "research_round": 0,
        "research_rounds": [],
    }
    timeout_context = asyncio.timeout(AUDIT_TIMEOUT)
    try:
        async with timeout_context:
            state = await graph.ainvoke(initial)
    except TimeoutError as exc:
        if not timeout_context.expired():
            raise
        raise AgenticAuditTimeoutError(
            f"agentic audit exceeded the {AUDIT_TIMEOUT}-second deadline"
        ) from exc
    return AgenticAuditResult(
        target_url=state["normalized_target_url"],
        crawl_result=state["crawl_result"],
        machine_readable_audit=state["machine_readable_audit"],
        brand_profile=state["brand_profile"],
        claim_evidence_map=state["claim_evidence_map"],
        query_set=state["query_set"],
        external_research=state["external_research"],
        query_evaluations=state["query_evaluations"],
        research_rounds=state["research_rounds"],
        evidence_gaps=state["evidence_gaps"],
        experiments=state["experiments"],
        metrics=state["metrics"],
        execution_trace=state["execution_trace"],
    )
