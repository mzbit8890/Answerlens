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
from schemas.query import (
    MAX_QUERIES,
    MAX_EXTERNAL_URL_LENGTH,
    QueryEvaluationSet,
    RecommendationQuery,
    RecommendationQuerySet,
    SourceOwnership,
)

MAX_RESULTS_PER_QUERY = 5
MAX_RESULT_TITLE_LENGTH = 500
MAX_RESULT_CONTENT_LENGTH = 4_000

ResultTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_RESULT_TITLE_LENGTH)
]
ResultContent = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_RESULT_CONTENT_LENGTH)
]
ResultDomain = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=253)
]


class ExternalSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    domain: ResultDomain
    title: ResultTitle
    content: ResultContent
    source_ownership: SourceOwnership
    relevance_score: float | None = Field(default=None, ge=0, le=1)

    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("search result URL must be a string")
        if len(value.strip()) > MAX_EXTERNAL_URL_LENGTH:
            raise ValueError("search result URL exceeds the length limit")
        try:
            return validate_url_reference(value)
        except URLSafetyError as exc:
            raise ValueError(f"invalid search result URL: {exc}") from exc


class ResearchStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class QueryResearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: RecommendationQuery
    status: ResearchStatus
    results: list[ExternalSearchResult] = Field(
        default_factory=list, max_length=MAX_RESULTS_PER_QUERY
    )
    discarded_results: int = Field(default=0, ge=0)
    error: str | None = None

    @model_validator(mode="after")
    def enforce_retrieval_state(self) -> "QueryResearchResult":
        if self.status is ResearchStatus.FAILED:
            if self.results:
                raise ValueError("failed research cannot contain results")
            if not self.error:
                raise ValueError("failed research requires an error")
        elif self.error is not None:
            raise ValueError("completed research cannot contain an error")
        return self


class ExternalResearchBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_results: list[QueryResearchResult] = Field(
        default_factory=list, max_length=MAX_QUERIES
    )


class ExternalGeoEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_set: RecommendationQuerySet
    research: ExternalResearchBatch
    evaluations: QueryEvaluationSet
