from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from guardrails.url_safety import URLSafetyError, validate_url_reference
from schemas.agentic import AgentEvent, AuditMetrics, EvidenceGapSet, GeoExperimentSet, ResearchRound
from schemas.brand import BrandProfile
from schemas.evidence import ClaimEvidenceMap
from schemas.machine_readable import MachineReadableSummary
from schemas.query import QueryEvaluationSet, RecommendationQuerySet
from schemas.research import ExternalResearchBatch

MAX_CATEGORY_LENGTH = 200
MAX_KNOWN_COMPETITORS = 10
MAX_COMPETITOR_LENGTH = 200
MAX_ERROR_MESSAGE_LENGTH = 500

NonEmptyCategory = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_CATEGORY_LENGTH)]
Competitor = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_COMPETITOR_LENGTH)]


class AuditStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DeltaDirection(StrEnum):
    IMPROVED = "improved"
    REGRESSED = "regressed"
    UNCHANGED = "unchanged"


class MetricDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    previous: float
    current: float
    delta: float
    direction: DeltaDirection


class AuditDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_coverage: MetricDelta
    query_readiness: MetricDelta
    strong_queries: MetricDelta
    evidence_gaps: MetricDelta
    external_evidence_diversity: MetricDelta
    new_gap_queries: list[str] = Field(default_factory=list, max_length=12)
    resolved_gap_queries: list[str] = Field(default_factory=list, max_length=12)


class PersistedAuditResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_url: str
    brand_profile: BrandProfile
    claim_evidence_map: ClaimEvidenceMap
    machine_readable: MachineReadableSummary
    query_set: RecommendationQuerySet
    external_research: ExternalResearchBatch
    query_evaluations: QueryEvaluationSet
    research_rounds: list[ResearchRound] = Field(default_factory=list, max_length=2)
    evidence_gaps: EvidenceGapSet
    experiments: GeoExperimentSet
    metrics: AuditMetrics
    execution_trace: list[AgentEvent] = Field(default_factory=list, max_length=50)


class AuditCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_url: str
    category: NonEmptyCategory | None = None
    known_competitors: list[Competitor] = Field(default_factory=list, max_length=MAX_KNOWN_COMPETITORS)

    @field_validator("target_url", mode="before")
    @classmethod
    def validate_target_reference(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("target_url must be a string")
        try:
            return validate_url_reference(value)
        except URLSafetyError as exc:
            raise ValueError(f"invalid target_url: {exc}") from exc

    @field_validator("known_competitors")
    @classmethod
    def deduplicate_competitors(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            key = " ".join(value.split()).casefold()
            if key not in seen:
                seen.add(key)
                result.append(value)
        return result


class AuditRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    target_url: str
    category: str | None = None
    known_competitors: list[str] = Field(default_factory=list, max_length=MAX_KNOWN_COMPETITORS)
    status: AuditStatus
    previous_audit_id: UUID | None = None
    result: PersistedAuditResult | None = None
    delta: AuditDelta | None = None
    error_code: str | None = None
    error_message: Annotated[str, StringConstraints(max_length=MAX_ERROR_MESSAGE_LENGTH)] | None = None
    created_at: datetime
    completed_at: datetime | None = None
