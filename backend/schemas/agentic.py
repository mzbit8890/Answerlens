from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from schemas.brand import BrandProfile
from schemas.crawl import CrawlResult
from schemas.evidence import ClaimEvidenceMap, ConfidenceLevel
from schemas.machine_readable import MachineReadableAudit
from schemas.query import (
    MAX_QUERIES,
    CompetitorEvidence,
    GroundedExternalEvidence,
    QueryEvaluationSet,
    ReadinessLevel,
    RecommendationQuerySet,
)
from schemas.research import ExternalResearchBatch, QueryResearchResult

MAX_RESEARCH_PLANS = MAX_QUERIES
MAX_RESEARCH_QUERY_LENGTH = 500
MAX_RESEARCH_REASON_LENGTH = 1_000
MAX_GAPS = MAX_QUERIES
MAX_GAP_TEXT_LENGTH = 2_000
MAX_GAP_LIST_ITEMS = 10
MAX_EXPERIMENTS = 6
MAX_EXPERIMENT_TEXT_LENGTH = 2_000
MAX_TRACE_EVENTS = 50
MAX_TRACE_MESSAGE_LENGTH = 500
MAX_TRACE_COUNTERS = 20

BoundedResearchQuery = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=MAX_RESEARCH_QUERY_LENGTH
    ),
]
BoundedReason = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=MAX_RESEARCH_REASON_LENGTH
    ),
]
BoundedGapText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_GAP_TEXT_LENGTH),
]
BoundedExperimentText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=MAX_EXPERIMENT_TEXT_LENGTH
    ),
]


class TargetedResearchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_query: BoundedResearchQuery
    search_query: BoundedResearchQuery
    reason: BoundedReason


class TargetedResearchPlanSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plans: list[TargetedResearchPlan] = Field(
        default_factory=list, max_length=MAX_RESEARCH_PLANS
    )

    @model_validator(mode="after")
    def reject_duplicates(self) -> "TargetedResearchPlanSet":
        originals = [plan.original_query for plan in self.plans]
        searches = [" ".join(plan.search_query.split()).casefold() for plan in self.plans]
        if len(originals) != len(set(originals)):
            raise ValueError("only one targeted plan is allowed per original query")
        if len(searches) != len(set(searches)):
            raise ValueError("targeted search queries must be unique")
        return self


class ResearchRound(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round_number: int = Field(ge=1, le=2)
    plans: TargetedResearchPlanSet
    results: list[QueryResearchResult] = Field(
        default_factory=list, max_length=MAX_RESEARCH_PLANS
    )


class EvidenceGap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: BoundedResearchQuery
    readiness: ReadinessLevel
    why: BoundedGapText
    missing_evidence: list[BoundedGapText] = Field(
        default_factory=list, max_length=MAX_GAP_LIST_ITEMS
    )
    supporting_sources: list[GroundedExternalEvidence] = Field(
        default_factory=list, max_length=MAX_GAP_LIST_ITEMS
    )
    stronger_competitors: list[CompetitorEvidence] = Field(
        default_factory=list, max_length=MAX_GAP_LIST_ITEMS
    )
    confidence: ConfidenceLevel

    @model_validator(mode="after")
    def require_weak_readiness(self) -> "EvidenceGap":
        if self.readiness is ReadinessLevel.HIGH:
            raise ValueError("high-readiness evaluations are not evidence gaps")
        return self


class EvidenceGapSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gaps: list[EvidenceGap] = Field(default_factory=list, max_length=MAX_GAPS)


class GeoExperiment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation: BoundedExperimentText
    hypothesis: BoundedExperimentText
    proposed_change: BoundedExperimentText
    evaluation_queries: list[BoundedResearchQuery] = Field(
        min_length=1, max_length=MAX_GAP_LIST_ITEMS
    )
    success_condition: BoundedExperimentText
    confidence: ConfidenceLevel


class GeoExperimentSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiments: list[GeoExperiment] = Field(
        default_factory=list, max_length=MAX_EXPERIMENTS
    )


class AuditMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_coverage: float = Field(ge=0, le=100)
    query_readiness: float = Field(ge=0, le=100)
    strong_queries: int = Field(ge=0)
    evidence_gaps: int = Field(ge=0)
    external_evidence_diversity: int = Field(ge=0)
    completed_evaluations: int = Field(ge=0)
    unavailable_evaluations: int = Field(ge=0)


class AgentEventStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


class AgentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]
    status: AgentEventStatus
    message: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=MAX_TRACE_MESSAGE_LENGTH
        ),
    ]
    duration_ms: int = Field(ge=0)
    counters: dict[str, int] = Field(default_factory=dict, max_length=MAX_TRACE_COUNTERS)


class AgenticAuditResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_url: str
    crawl_result: CrawlResult
    machine_readable_audit: MachineReadableAudit
    brand_profile: BrandProfile
    claim_evidence_map: ClaimEvidenceMap
    query_set: RecommendationQuerySet
    external_research: ExternalResearchBatch
    query_evaluations: QueryEvaluationSet
    research_rounds: list[ResearchRound] = Field(default_factory=list, max_length=2)
    evidence_gaps: EvidenceGapSet
    experiments: GeoExperimentSet
    metrics: AuditMetrics
    execution_trace: list[AgentEvent] = Field(
        default_factory=list, max_length=MAX_TRACE_EVENTS
    )


class AgenticAuditTimeoutError(TimeoutError):
    """The global agentic audit deadline expired."""
