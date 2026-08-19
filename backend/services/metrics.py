from urllib.parse import urlsplit

from schemas.agentic import AuditMetrics, EvidenceGapSet
from schemas.evidence import ClaimEvidenceMap, ClaimSupportStatus
from schemas.query import (
    EvaluationStatus,
    QueryEvaluationSet,
    ReadinessLevel,
    SourceOwnership,
)


def calculate_audit_metrics(
    claim_evidence_map: ClaimEvidenceMap,
    evaluations: QueryEvaluationSet,
    gaps: EvidenceGapSet,
) -> AuditMetrics:
    claim_count = len(claim_evidence_map.records)
    supported = sum(
        record.support_status is ClaimSupportStatus.SUPPORTED
        for record in claim_evidence_map.records
    )
    coverage = round((supported / claim_count * 100) if claim_count else 0.0, 1)

    completed = [
        evaluation
        for evaluation in evaluations.evaluations
        if evaluation.status is EvaluationStatus.COMPLETED
    ]
    weights = {
        ReadinessLevel.LOW: 0.0,
        ReadinessLevel.MEDIUM: 0.5,
        ReadinessLevel.HIGH: 1.0,
    }
    readiness = round(
        (
            sum(weights[evaluation.readiness] for evaluation in completed)  # type: ignore[index]
            / len(completed)
            * 100
        )
        if completed
        else 0.0,
        1,
    )
    independent_domains = {
        hostname
        for evaluation in completed
        for reference in evaluation.supporting_evidence
        if reference.source_ownership is SourceOwnership.INDEPENDENT
        if (hostname := urlsplit(reference.url).hostname) is not None
    }
    return AuditMetrics(
        evidence_coverage=coverage,
        query_readiness=readiness,
        strong_queries=sum(
            evaluation.readiness is ReadinessLevel.HIGH for evaluation in completed
        ),
        evidence_gaps=len(gaps.gaps),
        external_evidence_diversity=len(independent_domains),
        completed_evaluations=len(completed),
        unavailable_evaluations=sum(
            evaluation.status is EvaluationStatus.UNAVAILABLE
            for evaluation in evaluations.evaluations
        ),
    )
