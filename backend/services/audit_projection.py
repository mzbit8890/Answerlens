from schemas.agentic import AgenticAuditResult
from schemas.audit import AuditDelta, DeltaDirection, MetricDelta, PersistedAuditResult


def project_audit_result(result: AgenticAuditResult) -> PersistedAuditResult:
    return PersistedAuditResult(
        target_url=result.target_url,
        brand_profile=result.brand_profile,
        claim_evidence_map=result.claim_evidence_map,
        machine_readable=result.machine_readable_audit.summary,
        query_set=result.query_set,
        external_research=result.external_research,
        query_evaluations=result.query_evaluations,
        research_rounds=result.research_rounds,
        evidence_gaps=result.evidence_gaps,
        experiments=result.experiments,
        metrics=result.metrics,
        execution_trace=result.execution_trace,
    )


def _metric(previous: float, current: float, *, lower_is_better: bool = False) -> MetricDelta:
    delta = round(current - previous, 2)
    if delta == 0:
        direction = DeltaDirection.UNCHANGED
    elif (delta < 0) == lower_is_better:
        direction = DeltaDirection.IMPROVED
    else:
        direction = DeltaDirection.REGRESSED
    return MetricDelta(previous=previous, current=current, delta=delta, direction=direction)


def compare_audit_results(previous: PersistedAuditResult, current: PersistedAuditResult) -> AuditDelta:
    old = previous.metrics
    new = current.metrics
    old_gaps = {" ".join(gap.query.split()).casefold(): gap.query for gap in previous.evidence_gaps.gaps}
    new_gaps = {" ".join(gap.query.split()).casefold(): gap.query for gap in current.evidence_gaps.gaps}
    return AuditDelta(
        evidence_coverage=_metric(old.evidence_coverage, new.evidence_coverage),
        query_readiness=_metric(old.query_readiness, new.query_readiness),
        strong_queries=_metric(old.strong_queries, new.strong_queries),
        evidence_gaps=_metric(old.evidence_gaps, new.evidence_gaps, lower_is_better=True),
        external_evidence_diversity=_metric(old.external_evidence_diversity, new.external_evidence_diversity),
        new_gap_queries=[new_gaps[key] for key in sorted(new_gaps.keys() - old_gaps.keys())],
        resolved_gap_queries=[old_gaps[key] for key in sorted(old_gaps.keys() - new_gaps.keys())],
    )
