from collections.abc import Awaitable, Callable
from uuid import UUID

from graph.workflow import run_agentic_audit
from providers.gemini import GeminiConfigurationError, GeminiProviderError
from providers.search import SearchProviderError
from repositories.audit import AuditRepository, AuditRepositoryError
from schemas.agentic import AgenticAuditResult, AgenticAuditTimeoutError
from schemas.audit import AuditCreateRequest, AuditRecord, AuditStatus
from services.audit_projection import compare_audit_results, project_audit_result
from services.diagnostics import provider_status_code

WorkflowRunner = Callable[..., Awaitable[AgenticAuditResult]]


class AuditNotFoundError(LookupError): pass


class AuditExecutionError(RuntimeError):
    def __init__(self, audit: AuditRecord) -> None:
        super().__init__(audit.error_message)
        self.audit = audit


def classify_audit_failure(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, AgenticAuditTimeoutError): return "audit_timeout", "The audit exceeded its 120-second limit."
    if isinstance(exc, GeminiConfigurationError): return "gemini_not_configured", "Gemini is not configured for audits."
    if isinstance(exc, GeminiProviderError) and provider_status_code(exc) == 429: return "gemini_rate_limited", "AI provider rate limit reached. Please try again later."
    if isinstance(exc, GeminiProviderError): return "gemini_unavailable", "Gemini could not complete the audit. Please try again later."
    if isinstance(exc, SearchProviderError): return "search_unavailable", "External evidence search could not complete the audit."
    if isinstance(exc, ValueError): return "invalid_target", "The submitted audit target is invalid."
    return "audit_failed", "The audit could not be completed."


class AuditService:
    def __init__(self, repository: AuditRepository, workflow_runner: WorkflowRunner = run_agentic_audit) -> None:
        self.repository = repository
        self.workflow_runner = workflow_runner

    async def get(self, audit_id: UUID) -> AuditRecord:
        audit = await self.repository.get_audit(audit_id)
        if audit is None: raise AuditNotFoundError("audit not found")
        return audit

    async def run(self, request: AuditCreateRequest, previous_audit_id: UUID | None = None) -> AuditRecord:
        audit = await self.repository.create_running_audit(request.target_url, request.category, request.known_competitors, previous_audit_id)
        try:
            workflow_result = await self.workflow_runner(request.target_url, request.category, request.known_competitors)
            result = project_audit_result(workflow_result)
        except AuditRepositoryError:
            raise
        except Exception as exc:
            code, message = classify_audit_failure(exc)
            failed = await self.repository.fail_audit(audit.id, code, message)
            raise AuditExecutionError(failed) from exc

        delta = None
        if previous_audit_id:
            previous = await self.repository.get_audit(previous_audit_id)
            if previous and previous.status is AuditStatus.COMPLETED and previous.result:
                delta = compare_audit_results(previous.result, result)
        return await self.repository.complete_audit(audit.id, result, delta)

    async def rerun(self, audit_id: UUID) -> AuditRecord:
        previous = await self.get(audit_id)
        request = AuditCreateRequest(target_url=previous.target_url, category=previous.category, known_competitors=previous.known_competitors)
        return await self.run(request, previous.id)
