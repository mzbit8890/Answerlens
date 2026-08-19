from enum import StrEnum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from guardrails.url_safety import URLSafetyError, validate_url_reference
from schemas.evidence import ConfidenceLevel

MAX_QUERIES = 12
MAX_QUERY_LENGTH = 500
MAX_QUERY_RATIONALE_LENGTH = 1_000
MAX_EXTERNAL_EVIDENCE = 10
MAX_MISSING_EVIDENCE = 10
MAX_COMPETITOR_EVIDENCE = 10
MAX_COMPETITOR_NAME_LENGTH = 200
MAX_EVALUATION_REASON_LENGTH = 2_000
MAX_EXTERNAL_URL_LENGTH = 2_048

QueryText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_QUERY_LENGTH,
    ),
]

Rationale = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_QUERY_RATIONALE_LENGTH,
    ),
]

EvidenceExcerpt = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=2_000,
    ),
]

MissingEvidence = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=1_000,
    ),
]

CompetitorName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_COMPETITOR_NAME_LENGTH,
    ),
]

EvaluationReason = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_EVALUATION_REASON_LENGTH,
    ),
]


class QueryIntent(StrEnum):
    CATEGORY_DISCOVERY = "category_discovery"
    ALTERNATIVE_COMPARISON = "alternative_comparison"
    AUDIENCE_USE_CASE = "audience_use_case"
    PROBLEM_DRIVEN = "problem_driven"
    CAPABILITY_DRIVEN = "capability_driven"


class RecommendationQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: QueryText
    intent: QueryIntent
    rationale: Rationale


class RecommendationQuerySet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queries: list[RecommendationQuery] = Field(
        default_factory=list,
        max_length=MAX_QUERIES,
    )

    @model_validator(mode="after")
    def reject_duplicate_queries(self) -> "RecommendationQuerySet":
        normalized = [
            " ".join(item.query.split()).casefold()
            for item in self.queries
        ]

        if len(normalized) != len(set(normalized)):
            raise ValueError(
                "recommendation queries must be unique ignoring case and whitespace"
            )

        return self


class ReadinessLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EvaluationStatus(StrEnum):
    COMPLETED = "completed"
    UNAVAILABLE = "unavailable"


class SourceOwnership(StrEnum):
    BRAND_OWNED = "brand_owned"
    INDEPENDENT = "independent"


class GroundedExternalEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    excerpt: EvidenceExcerpt
    source_ownership: SourceOwnership

    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("external evidence URL must be a string")

        if len(value.strip()) > MAX_EXTERNAL_URL_LENGTH:
            raise ValueError(
                "external evidence URL exceeds the length limit"
            )

        try:
            return validate_url_reference(value)
        except URLSafetyError as exc:
            raise ValueError(
                f"invalid external evidence URL: {exc}"
            ) from exc


class CompetitorEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    competitor: CompetitorName

    evidence: list[GroundedExternalEvidence] = Field(
        default_factory=list,
        min_length=1,
        max_length=MAX_EXTERNAL_EVIDENCE,
    )

    reason: EvaluationReason


class QueryEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: QueryText
    status: EvaluationStatus

    readiness: ReadinessLevel | None = None

    supporting_evidence: list[GroundedExternalEvidence] = Field(
        default_factory=list,
        max_length=MAX_EXTERNAL_EVIDENCE,
    )

    missing_evidence: list[MissingEvidence] = Field(
        default_factory=list,
        max_length=MAX_MISSING_EVIDENCE,
    )

    competitor_evidence: list[CompetitorEvidence] = Field(
        default_factory=list,
        max_length=MAX_COMPETITOR_EVIDENCE,
    )

    confidence: ConfidenceLevel | None = None
    reason: EvaluationReason | None = None

    @model_validator(mode="after")
    def enforce_status_fields(self) -> "QueryEvaluation":
        if self.status is EvaluationStatus.COMPLETED:
            if (
                self.readiness is None
                or self.confidence is None
                or self.reason is None
            ):
                raise ValueError(
                    "completed evaluations require readiness, confidence, and reason"
                )

            if (
                self.readiness
                in {
                    ReadinessLevel.MEDIUM,
                    ReadinessLevel.HIGH,
                }
                and not self.supporting_evidence
            ):
                raise ValueError(
                    "medium and high readiness require supporting external evidence"
                )

        elif any(
            (
                self.readiness is not None,
                bool(self.supporting_evidence),
                bool(self.missing_evidence),
                bool(self.competitor_evidence),
                self.confidence is not None,
            )
        ):
            raise ValueError(
                "unavailable evaluations cannot contain evidence judgments"
            )

        return self


class QueryEvaluationSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluations: list[QueryEvaluation] = Field(
        default_factory=list,
        max_length=MAX_QUERIES,
    )