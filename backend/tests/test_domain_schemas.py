import json

import pytest
from pydantic import ValidationError

from schemas.brand import (
    MAX_AUDIENCES,
    MAX_BRAND_CLAIMS,
    MAX_CAPABILITIES,
    MAX_CLAIM_LENGTH,
    MAX_USE_CASES,
    BrandClaim,
    BrandProfile,
)
from schemas.evidence import (
    MAX_EVIDENCE_PER_CLAIM,
    ClaimEvidence,
    ClaimSupportStatus,
    ConfidenceLevel,
    EvidenceReference,
    EvidenceSourceType,
)


def evidence_reference(url: str = "https://example.com/product") -> EvidenceReference:
    return EvidenceReference(
        url=url,
        excerpt="Example provides issue tracking for software teams.",
        source_type=EvidenceSourceType.OWNED_WEBPAGE,
    )


def test_valid_complete_brand_profile() -> None:
    profile = BrandProfile(
        brand="  Example  ",
        category="Project management software",
        audiences=["Software teams", "Product teams"],
        capabilities=["Issue tracking", "Project planning"],
        use_cases=["Planning a product launch"],
        positioning="A planning tool for software teams.",
        claims=[BrandClaim(statement="Example provides issue tracking.")],
    )

    assert profile.brand == "Example"
    assert profile.audiences == ["Software teams", "Product teams"]
    assert profile.claims[0].statement == "Example provides issue tracking."


def test_brand_profile_allows_optional_information_to_be_absent() -> None:
    profile = BrandProfile(brand="Example")

    assert profile.category is None
    assert profile.positioning is None
    assert profile.audiences == []
    assert profile.capabilities == []
    assert profile.use_cases == []
    assert profile.claims == []


def test_empty_required_brand_is_rejected() -> None:
    with pytest.raises(ValidationError):
        BrandProfile(brand="   ")


@pytest.mark.parametrize("field", ["audiences", "capabilities", "use_cases"])
def test_whitespace_only_list_entries_are_rejected(field: str) -> None:
    with pytest.raises(ValidationError):
        BrandProfile(brand="Example", **{field: ["   "]})


@pytest.mark.parametrize(
    ("field", "limit", "value"),
    [
        ("audiences", MAX_AUDIENCES, "Audience"),
        ("capabilities", MAX_CAPABILITIES, "Capability"),
        ("use_cases", MAX_USE_CASES, "Use case"),
        ("claims", MAX_BRAND_CLAIMS, BrandClaim(statement="A claim")),
    ],
)
def test_brand_profile_list_limits_are_enforced(
    field: str, limit: int, value: str | BrandClaim
) -> None:
    with pytest.raises(ValidationError):
        BrandProfile(brand="Example", **{field: [value] * (limit + 1)})


def test_brand_profile_rejects_unexpected_fields() -> None:
    with pytest.raises(ValidationError):
        BrandProfile(brand="Example", invented="not allowed")


def test_valid_claim_is_trimmed_without_rewriting() -> None:
    claim = BrandClaim(statement="  Example supports planning.  ")

    assert claim.statement == "Example supports planning."


def test_empty_and_excessively_long_claims_are_rejected() -> None:
    with pytest.raises(ValidationError):
        BrandClaim(statement=" ")

    with pytest.raises(ValidationError):
        BrandClaim(statement="x" * (MAX_CLAIM_LENGTH + 1))


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/page",
        "https://example.com/page",
    ],
)
def test_valid_http_and_https_evidence_urls(url: str) -> None:
    reference = evidence_reference(url)

    assert reference.url.startswith(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/source",
        "http://127.0.0.1/source",
        "http://10.0.0.5/source",
    ],
)
def test_non_public_literal_and_local_evidence_urls_are_rejected(url: str) -> None:
    with pytest.raises(ValidationError):
        evidence_reference(url)


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/file",
        "not a url",
        "/relative",
        "https://",
    ],
)
def test_malformed_and_non_http_evidence_urls_are_rejected(url: str) -> None:
    with pytest.raises(ValidationError):
        evidence_reference(url)


def test_credential_bearing_evidence_url_is_rejected() -> None:
    with pytest.raises(ValidationError):
        evidence_reference("https://user:secret@example.com/private")


def test_evidence_excerpt_is_required_and_non_empty() -> None:
    with pytest.raises(ValidationError):
        EvidenceReference(
            url="https://example.com/product",
            excerpt="   ",
            source_type=EvidenceSourceType.OWNED_WEBPAGE,
        )


def test_evidence_source_type_uses_explicit_enum() -> None:
    reference = evidence_reference()

    assert reference.source_type is EvidenceSourceType.OWNED_WEBPAGE

    with pytest.raises(ValidationError):
        EvidenceReference(
            url="https://example.com/product",
            excerpt="Evidence",
            source_type="invented_source",
        )


def test_supported_claim_with_evidence_is_representable() -> None:
    mapping = ClaimEvidence(
        claim=BrandClaim(statement="Example provides issue tracking."),
        support_status=ClaimSupportStatus.SUPPORTED,
        evidence=[evidence_reference()],
        confidence=ConfidenceLevel.HIGH,
        confidence_reason="The product page states the capability directly.",
    )

    assert mapping.support_status is ClaimSupportStatus.SUPPORTED
    assert len(mapping.evidence) == 1


@pytest.mark.parametrize(
    "status",
    [
        ClaimSupportStatus.INSUFFICIENT_EVIDENCE,
        ClaimSupportStatus.ASSUMPTION,
    ],
)
def test_uncertain_claim_states_allow_zero_evidence(
    status: ClaimSupportStatus,
) -> None:
    mapping = ClaimEvidence(
        claim=BrandClaim(statement="Example is designed for agencies."),
        support_status=status,
        confidence=ConfidenceLevel.LOW,
        confidence_reason="No direct source supports this proposition.",
    )

    assert mapping.evidence == []


def test_supported_claim_cannot_silently_omit_evidence() -> None:
    with pytest.raises(ValidationError, match="require at least one evidence"):
        ClaimEvidence(
            claim=BrandClaim(statement="Example provides issue tracking."),
            support_status=ClaimSupportStatus.SUPPORTED,
            confidence=ConfidenceLevel.HIGH,
            confidence_reason="Directly stated.",
        )


def test_confidence_is_limited_to_low_medium_high() -> None:
    with pytest.raises(ValidationError):
        ClaimEvidence(
            claim=BrandClaim(statement="A proposition"),
            support_status=ClaimSupportStatus.ASSUMPTION,
            confidence="certain",
            confidence_reason="This value is intentionally invalid.",
        )


def test_confidence_reason_must_be_non_empty() -> None:
    with pytest.raises(ValidationError):
        ClaimEvidence(
            claim=BrandClaim(statement="A proposition"),
            support_status=ClaimSupportStatus.ASSUMPTION,
            confidence=ConfidenceLevel.LOW,
            confidence_reason="   ",
        )


def test_nested_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ClaimEvidence.model_validate(
            {
                "claim": {
                    "statement": "A proposition",
                    "verified": True,
                },
                "support_status": "assumption",
                "confidence": "low",
                "confidence_reason": "No supporting source.",
            }
        )


def test_excessive_evidence_list_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ClaimEvidence(
            claim=BrandClaim(statement="A proposition"),
            support_status=ClaimSupportStatus.SUPPORTED,
            evidence=[evidence_reference()] * (MAX_EVIDENCE_PER_CLAIM + 1),
            confidence=ConfidenceLevel.HIGH,
            confidence_reason="Evidence list exceeds the contract limit.",
        )


def test_model_json_serialization_is_clean_and_deterministic() -> None:
    mapping = ClaimEvidence(
        claim=BrandClaim(statement="Example provides issue tracking."),
        support_status=ClaimSupportStatus.SUPPORTED,
        evidence=[evidence_reference()],
        confidence=ConfidenceLevel.HIGH,
        confidence_reason="The product page states the capability directly.",
    )

    serialized = mapping.model_dump_json()

    assert serialized == mapping.model_dump_json()

    assert json.loads(serialized) == {
        "claim": {
            "statement": "Example provides issue tracking.",
        },
        "support_status": "supported",
        "evidence": [
            {
                "url": "https://example.com/product",
                "excerpt": "Example provides issue tracking for software teams.",
                "source_type": "owned_webpage",
            }
        ],
        "confidence": "high",
        "confidence_reason": "The product page states the capability directly.",
    }