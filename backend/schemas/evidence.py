from enum import StrEnum
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from guardrails.url_safety import URLSafetyError, validate_url_reference
from schemas.brand import BrandClaim

MAX_EVIDENCE_PER_CLAIM = 10
MAX_EVIDENCE_URL_LENGTH = 2_048
MAX_EVIDENCE_EXCERPT_LENGTH = 2_000
MAX_CONFIDENCE_REASON_LENGTH = 1_000

EvidenceExcerpt = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_EVIDENCE_EXCERPT_LENGTH,
    ),
]
ConfidenceReason = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MAX_CONFIDENCE_REASON_LENGTH,
    ),
]




class EvidenceSourceType(StrEnum):
    OWNED_WEBPAGE = "owned_webpage"
    STRUCTURED_DATA = "structured_data"
    LLMS_TXT = "llms_txt"
    BRAND_OWNED_EXTERNAL = "brand_owned_external"
    INDEPENDENT_EXTERNAL = "independent_external"


class ClaimSupportStatus(StrEnum):
    SUPPORTED = "supported"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    ASSUMPTION = "assumption"


class ConfidenceLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    excerpt: EvidenceExcerpt
    source_type: EvidenceSourceType

    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("evidence URL must be a string")
        candidate = value.strip()
        if not candidate or len(candidate) > MAX_EVIDENCE_URL_LENGTH:
            raise ValueError("evidence URL must be non-empty and within the length limit")
        try:
           return validate_url_reference(candidate)
        except URLSafetyError as exc:
           raise ValueError(f"invalid evidence URL: {exc}") from exc


class ClaimEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: BrandClaim
    support_status: ClaimSupportStatus
    evidence: list[EvidenceReference] = Field(
        default_factory=list, max_length=MAX_EVIDENCE_PER_CLAIM
    )
    confidence: ConfidenceLevel
    confidence_reason: ConfidenceReason

    @model_validator(mode="after")
    def supported_claim_requires_evidence(self) -> "ClaimEvidence":
        if self.support_status is ClaimSupportStatus.SUPPORTED and not self.evidence:
            raise ValueError("supported claims require at least one evidence reference")
        return self
