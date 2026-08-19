import asyncio
import inspect
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from main import app, get_audit_service
from providers.gemini import GeminiRequestError
from providers.search import SearchRequestError
import repositories.audit as audit_repository_module
from repositories.audit import AuditRepositoryError, PostgresAuditRepository
from schemas.agentic import AgentEvent, AgentEventStatus, AgenticAuditResult, AgenticAuditTimeoutError, AuditMetrics, EvidenceGap, EvidenceGapSet, GeoExperimentSet
from schemas.audit import AuditCreateRequest, AuditRecord, AuditStatus, DeltaDirection
from schemas.brand import BrandProfile
from schemas.crawl import CrawlResult
from schemas.evidence import ClaimEvidenceMap, ConfidenceLevel
from schemas.machine_readable import LlmsTxtInspection, MachineReadableAudit, MachineReadableSummary, ParseStatus, RobotsInspection, SitemapInspection, StructuredDataInspection, SurfaceStatus
from schemas.query import EvaluationStatus, QueryEvaluation, QueryEvaluationSet, QueryIntent, ReadinessLevel, RecommendationQuery, RecommendationQuerySet
from schemas.research import ExternalResearchBatch
from services.audit_projection import compare_audit_results, project_audit_result
from services.audit_service import AuditExecutionError, AuditService


def workflow_result(*, coverage=60, readiness=50, strong=1, gaps=1, diversity=2, gap_query="Missing query"):
    summary = MachineReadableSummary(robots_status=SurfaceStatus.MISSING, sitemap_status=SurfaceStatus.MISSING, sitemap_urls_discovered=0, llms_txt_status=SurfaceStatus.MISSING, llms_txt_links_discovered=0, structured_data_status=SurfaceStatus.MISSING, structured_data_pages=0)
    machine = MachineReadableAudit(target_url="https://example.com/", robots=RobotsInspection(source_url="https://example.com/robots.txt", status=SurfaceStatus.MISSING, parse_status=ParseStatus.NOT_APPLICABLE), sitemap=SitemapInspection(status=SurfaceStatus.MISSING), llms_txt=LlmsTxtInspection(source_url="https://example.com/llms.txt", status=SurfaceStatus.MISSING), structured_data=StructuredDataInspection(status=SurfaceStatus.MISSING), summary=summary)
    query = RecommendationQuery(query=gap_query, intent=QueryIntent.CATEGORY_DISCOVERY, rationale="Useful recommendation intent")
    evaluation = QueryEvaluation(query=gap_query, status=EvaluationStatus.COMPLETED, readiness=ReadinessLevel.LOW, confidence=ConfidenceLevel.HIGH, reason="Evidence is incomplete", missing_evidence=["Independent support"])
    gap = EvidenceGap(query=gap_query, readiness=ReadinessLevel.LOW, why="Independent support is missing", missing_evidence=["Independent support"], confidence=ConfidenceLevel.HIGH)
    return AgenticAuditResult(target_url="https://example.com/", crawl_result=CrawlResult(target_url="https://example.com/"), machine_readable_audit=machine, brand_profile=BrandProfile(brand="Example", category="Software"), claim_evidence_map=ClaimEvidenceMap(), query_set=RecommendationQuerySet(queries=[query]), external_research=ExternalResearchBatch(), query_evaluations=QueryEvaluationSet(evaluations=[evaluation]), evidence_gaps=EvidenceGapSet(gaps=[gap] if gaps else []), experiments=GeoExperimentSet(), metrics=AuditMetrics(evidence_coverage=coverage, query_readiness=readiness, strong_queries=strong, evidence_gaps=gaps, external_evidence_diversity=diversity, completed_evaluations=1, unavailable_evaluations=0), execution_trace=[AgentEvent(stage="audit_complete", status=AgentEventStatus.COMPLETED, message="Complete", duration_ms=1)])


class FakeRepository:
    def __init__(self): self.records: dict[UUID, AuditRecord] = {}
    async def create_running_audit(self, target_url, category, known_competitors, previous_audit_id=None):
        record = AuditRecord(id=uuid4(), target_url=target_url, category=category, known_competitors=known_competitors, status=AuditStatus.RUNNING, previous_audit_id=previous_audit_id, created_at=datetime.now(timezone.utc))
        self.records[record.id] = record
        return record
    async def get_audit(self, audit_id): return self.records.get(audit_id)
    async def complete_audit(self, audit_id, result, delta):
        old = self.records[audit_id]
        record = old.model_copy(update={"status": AuditStatus.COMPLETED, "result": result, "delta": delta, "completed_at": datetime.now(timezone.utc)})
        self.records[audit_id] = record
        return record
    async def fail_audit(self, audit_id, error_code, error_message):
        old = self.records[audit_id]
        record = old.model_copy(update={"status": AuditStatus.FAILED, "result": None, "delta": None, "error_code": error_code, "error_message": error_message, "completed_at": datetime.now(timezone.utc)})
        self.records[audit_id] = record
        return record


def test_service_persists_safe_completed_projection():
    repo = FakeRepository()
    async def runner(*args): return workflow_result()
    audit = asyncio.run(AuditService(repo, runner).run(AuditCreateRequest(target_url="https://example.com", known_competitors=["Acme"])))
    assert audit.status is AuditStatus.COMPLETED
    assert audit.result.brand_profile.brand == "Example"
    serialized = str(audit.model_dump(mode="json"))
    assert "GEMINI_API_KEY" not in serialized and "DATABASE_URL" not in serialized


def test_service_failure_is_persisted_without_fake_result():
    repo = FakeRepository()
    async def runner(*args): raise RuntimeError("secret provider payload")
    with pytest.raises(AuditExecutionError) as caught:
        asyncio.run(AuditService(repo, runner).run(AuditCreateRequest(target_url="https://example.com")))
    assert caught.value.audit.status is AuditStatus.FAILED
    assert caught.value.audit.result is None
    assert "secret provider payload" not in caught.value.audit.error_message


def test_rerun_creates_linked_new_record_and_delta():
    repo = FakeRepository()
    results = iter([workflow_result(coverage=50, gap_query="Old gap"), workflow_result(coverage=70, readiness=60, strong=2, gap_query="New gap")])
    async def runner(*args): return next(results)
    service = AuditService(repo, runner)
    first = asyncio.run(service.run(AuditCreateRequest(target_url="https://example.com", category="Software", known_competitors=["Acme"])))
    second = asyncio.run(service.rerun(first.id))
    assert second.id != first.id and second.previous_audit_id == first.id
    assert second.category == first.category and second.known_competitors == first.known_competitors
    assert second.delta.evidence_coverage.delta == 20
    assert second.delta.evidence_coverage.direction is DeltaDirection.IMPROVED
    assert second.delta.new_gap_queries == ["New gap"]
    assert second.delta.resolved_gap_queries == ["Old gap"]
    assert repo.records[first.id].result.metrics.evidence_coverage == 50


def test_delta_direction_handles_gap_reduction():
    previous = project_audit_result(workflow_result())
    current_raw = workflow_result()
    current_raw.metrics.evidence_gaps = 0
    current_raw.evidence_gaps = EvidenceGapSet()
    delta = compare_audit_results(previous, project_audit_result(current_raw))
    assert delta.evidence_gaps.delta == -1
    assert delta.evidence_gaps.direction is DeltaDirection.IMPROVED


@pytest.mark.parametrize(
    ("field", "previous", "current", "direction"),
    [
        ("evidence_coverage", 60, 75, DeltaDirection.IMPROVED),
        ("evidence_coverage", 60, 45, DeltaDirection.REGRESSED),
        ("query_readiness", 50, 65, DeltaDirection.IMPROVED),
        ("strong_queries", 2, 1, DeltaDirection.REGRESSED),
        ("evidence_gaps", 2, 3, DeltaDirection.REGRESSED),
        ("external_evidence_diversity", 2, 4, DeltaDirection.IMPROVED),
        ("query_readiness", 50, 50, DeltaDirection.UNCHANGED),
    ],
)
def test_each_metric_delta_direction(field, previous, current, direction):
    old_kwargs = {"coverage": 60, "readiness": 50, "strong": 2, "gaps": 2, "diversity": 2}
    new_kwargs = dict(old_kwargs)
    names = {"evidence_coverage": "coverage", "query_readiness": "readiness", "strong_queries": "strong", "evidence_gaps": "gaps", "external_evidence_diversity": "diversity"}
    old_kwargs[names[field]] = previous
    new_kwargs[names[field]] = current
    delta = compare_audit_results(project_audit_result(workflow_result(**old_kwargs)), project_audit_result(workflow_result(**new_kwargs)))
    assert getattr(delta, field).direction is direction


@pytest.mark.parametrize(
    ("failure", "code", "message"),
    [
        (AgenticAuditTimeoutError("timed out"), "audit_timeout", "120-second limit"),
        (GeminiRequestError("raw Gemini payload"), "gemini_unavailable", "Gemini could not complete"),
        (SearchRequestError("raw Tavily payload"), "search_unavailable", "External evidence search"),
    ],
)
def test_expected_workflow_failures_are_safely_persisted(failure, code, message):
    repo = FakeRepository()
    async def runner(*args): raise failure
    with pytest.raises(AuditExecutionError) as caught:
        asyncio.run(AuditService(repo, runner).run(AuditCreateRequest(target_url="https://example.com")))
    audit = caught.value.audit
    assert audit.status is AuditStatus.FAILED and audit.result is None and audit.delta is None
    assert audit.error_code == code and message in audit.error_message
    assert str(failure) not in audit.error_message


def gemini_rate_limit_failure(raw_message="RESOURCE_EXHAUSTED quota project detail"):
    class GoogleRateLimitError(RuntimeError):
        status_code = 429

    cause = GoogleRateLimitError(raw_message)
    failure = GeminiRequestError("Gemini structured-output request failed")
    failure.__cause__ = cause
    return failure


def test_gemini_429_is_safely_persisted_as_rate_limited():
    repo = FakeRepository()
    failure = gemini_rate_limit_failure()
    async def runner(*args): raise failure

    with pytest.raises(AuditExecutionError) as caught:
        asyncio.run(AuditService(repo, runner).run(AuditCreateRequest(target_url="https://example.com")))

    audit = caught.value.audit
    assert audit.status is AuditStatus.FAILED and audit.result is None
    assert audit.error_code == "gemini_rate_limited"
    assert audit.error_message == "AI provider rate limit reached. Please try again later."
    assert "RESOURCE_EXHAUSTED" not in str(audit.model_dump(mode="json"))


def test_gemini_429_api_response_excludes_raw_provider_details():
    repo = FakeRepository()
    raw_message = "RESOURCE_EXHAUSTED billing and quota internals"
    async def runner(*args): raise gemini_rate_limit_failure(raw_message)
    app.dependency_overrides[get_audit_service] = lambda: AuditService(repo, runner)
    try:
        response = TestClient(app).post("/audits", json={"target_url": "https://example.com"})
        assert response.status_code == 503
        detail = response.json()["detail"]
        assert detail["code"] == "gemini_rate_limited"
        assert detail["message"] == "AI provider rate limit reached. Please try again later."
        assert detail["audit"]["status"] == "failed"
        assert raw_message not in str(detail)
    finally:
        app.dependency_overrides.clear()


def test_repository_completion_failure_propagates_without_fail_write():
    class FailingRepository(FakeRepository):
        def __init__(self): super().__init__(); self.fail_writes = 0
        async def complete_audit(self, *args): raise AuditRepositoryError("database offline")
        async def fail_audit(self, *args): self.fail_writes += 1; return await super().fail_audit(*args)
    repo = FailingRepository()
    async def runner(*args): return workflow_result()
    with pytest.raises(AuditRepositoryError, match="database offline"):
        asyncio.run(AuditService(repo, runner).run(AuditCreateRequest(target_url="https://example.com")))
    assert repo.fail_writes == 0


def test_repository_previous_lookup_failure_is_not_misclassified():
    class FailingLookupRepository(FakeRepository):
        def __init__(self): super().__init__(); self.fail_writes = 0
        async def get_audit(self, audit_id): raise AuditRepositoryError("lookup unavailable")
        async def fail_audit(self, *args): self.fail_writes += 1; return await super().fail_audit(*args)
    repo = FailingLookupRepository()
    async def runner(*args): return workflow_result()
    with pytest.raises(AuditRepositoryError, match="lookup unavailable"):
        asyncio.run(AuditService(repo, runner).run(AuditCreateRequest(target_url="https://example.com"), uuid4()))
    assert repo.fail_writes == 0


def test_failed_previous_audit_produces_no_fabricated_delta():
    repo = FakeRepository()
    async def failing(*args): raise RuntimeError("workflow failed")
    service = AuditService(repo, failing)
    with pytest.raises(AuditExecutionError) as caught:
        asyncio.run(service.run(AuditCreateRequest(target_url="https://example.com", category="Software", known_competitors=["Acme"])))
    original = caught.value.audit
    async def successful(*args): return workflow_result()
    service.workflow_runner = successful
    rerun = asyncio.run(service.rerun(original.id))
    assert rerun.previous_audit_id == original.id and rerun.delta is None
    assert repo.records[original.id].status is AuditStatus.FAILED


def test_api_create_get_missing_and_rerun():
    repo = FakeRepository()
    async def runner(*args): return workflow_result()
    service = AuditService(repo, runner)
    app.dependency_overrides[get_audit_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.post("/audits", json={"target_url": "https://example.com", "known_competitors": ["Acme"]})
        assert response.status_code == 200
        audit_id = response.json()["id"]
        assert client.get(f"/audits/{audit_id}").status_code == 200
        rerun = client.post(f"/audits/{audit_id}/rerun")
        assert rerun.status_code == 200
        assert rerun.json()["id"] != audit_id
        assert rerun.json()["previous_audit_id"] == audit_id
        assert client.get(f"/audits/{uuid4()}").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_api_failure_returns_safe_failed_audit():
    repo = FakeRepository()
    async def runner(*args): raise RuntimeError("raw secret")
    app.dependency_overrides[get_audit_service] = lambda: AuditService(repo, runner)
    try:
        response = TestClient(app).post("/audits", json={"target_url": "https://example.com"})
        assert response.status_code == 503
        detail = response.json()["detail"]
        assert detail["audit"]["status"] == "failed" and detail["audit"]["result"] is None
        assert "raw secret" not in str(detail)
    finally: app.dependency_overrides.clear()


def test_health_and_missing_database_configuration(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    response = client.post("/audits", json={"target_url": "https://example.com"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "database_not_configured"


def postgres_row(**updates):
    row = {
        "id": uuid4(),
        "target_url": "https://example.com/",
        "category": None,
        "known_competitors": [],
        "status": "running",
        "previous_audit_id": None,
        "result": None,
        "delta": None,
        "error_code": None,
        "error_message": None,
        "created_at": datetime.now(timezone.utc),
        "completed_at": None,
    }
    row.update(updates)
    return row


def test_postgres_repository_methods_remain_async_and_dispatch_to_thread(monkeypatch):
    repository = PostgresAuditRepository("postgresql://configured-but-not-used")
    calls = []
    row = postgres_row()
    monkeypatch.setattr(repository, "_execute_sync", lambda *args, **kwargs: row)

    async def fake_to_thread(function, *args, **kwargs):
        calls.append((function, args, kwargs))
        return function(*args, **kwargs)

    monkeypatch.setattr(audit_repository_module.asyncio, "to_thread", fake_to_thread)
    audit = asyncio.run(repository.get_audit(row["id"]))

    assert inspect.iscoroutinefunction(repository.get_audit)
    assert inspect.iscoroutinefunction(repository.create_running_audit)
    assert audit == AuditRecord.model_validate(row)
    assert len(calls) == 1 and calls[0][0] == repository._execute_sync


def test_synchronous_psycopg_execution_uses_parameterized_cursor_and_cleanup(monkeypatch):
    events = []
    row = postgres_row()

    class Cursor:
        def __enter__(self): events.append("cursor_enter"); return self
        def __exit__(self, *args): events.append("cursor_exit")
        def execute(self, query, params): events.append((query, params))
        def fetchone(self): return row

    class Connection:
        def __enter__(self): events.append("connection_enter"); return self
        def __exit__(self, *args): events.append("connection_exit")
        def cursor(self): return Cursor()

    monkeypatch.setattr(audit_repository_module.psycopg, "connect", lambda database_url, row_factory: Connection())
    result = PostgresAuditRepository("postgresql://configured-but-not-used")._execute_sync("SELECT * FROM audits WHERE id = %s", (row["id"],))

    assert result == row
    assert events == ["connection_enter", "cursor_enter", ("SELECT * FROM audits WHERE id = %s", (row["id"],)), "cursor_exit", "connection_exit"]


def test_psycopg_error_is_sanitized_as_repository_error(monkeypatch):
    secret_url = "postgresql://private-user:private-password@db.example/audits"
    def fail_connect(*args, **kwargs):
        raise audit_repository_module.psycopg.OperationalError(f"could not connect to {secret_url}")
    monkeypatch.setattr(audit_repository_module.psycopg, "connect", fail_connect)

    with pytest.raises(AuditRepositoryError) as caught:
        asyncio.run(PostgresAuditRepository(secret_url).get_audit(uuid4()))

    assert str(caught.value) == "PostgreSQL audit operation failed"
    assert secret_url not in str(caught.value)


def test_postgres_completion_preserves_validated_update_semantics(monkeypatch):
    repository = PostgresAuditRepository("postgresql://configured-but-not-used")
    result = project_audit_result(workflow_result())
    calls = []

    def complete(query, params, *, fetch=True):
        calls.append((query, params, fetch))
        return postgres_row(id=params[-1], status="completed", result=result.model_dump(mode="json"), completed_at=params[-2])

    monkeypatch.setattr(repository, "_execute_sync", complete)
    audit_id = uuid4()
    audit = asyncio.run(repository.complete_audit(audit_id, result, None))

    assert audit.status is AuditStatus.COMPLETED and audit.result == result
    assert "UPDATE audits SET status=%s" in calls[0][0]
    assert calls[0][1][0] == "completed" and calls[0][1][-1] == audit_id
