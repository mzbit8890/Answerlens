import asyncio
import logging

import pytest
from pydantic import BaseModel, ValidationError

from providers.gemini import GeminiRequestError, GeminiStructuredOutputError
from services.diagnostics import diagnostic_node, log_workflow_failure


class UpstreamProviderError(RuntimeError):
    status_code = 429


def request_failure(secret: str) -> GeminiRequestError:
    try:
        raise UpstreamProviderError(f"quota exhausted for credential {secret}")
    except UpstreamProviderError as cause:
        error = GeminiRequestError("Gemini structured-output request failed")
        error.__cause__ = cause
        return error


def test_diagnostic_node_logs_stage_kind_status_and_sanitized_cause(
    monkeypatch, caplog
):
    secret = "diagnostic-test-secret"
    monkeypatch.setenv("GEMINI_API_KEY", secret)
    failure = request_failure(secret)

    async def failing_node():
        raise failure

    with caplog.at_level(logging.ERROR, logger="answerlens.workflow"):
        with pytest.raises(GeminiRequestError) as caught:
            asyncio.run(
                diagnostic_node("extract_brand_profile", failing_node)()
            )

    assert caught.value is failure
    message = caplog.messages[-1]
    assert "stage=extract_brand_profile" in message
    assert "failure_kind=provider_request" in message
    assert "exception_class=GeminiRequestError" in message
    assert "cause_class=UpstreamProviderError" in message
    assert "provider_status_code=429" in message
    assert "[REDACTED]" in message
    assert secret not in message


def test_structured_output_validation_is_classified_without_raw_credentials(
    monkeypatch, caplog
):
    class RequiredOutput(BaseModel):
        value: int

    secret_database_url = "postgresql://private:password@db.example/audits"
    monkeypatch.setenv("DATABASE_URL", secret_database_url)
    try:
        RequiredOutput.model_validate({})
    except ValidationError as cause:
        failure = GeminiStructuredOutputError("invalid structured output")
        failure.__cause__ = cause

    with caplog.at_level(logging.ERROR, logger="answerlens.workflow"):
        log_workflow_failure("build_claim_evidence_map", failure)

    message = caplog.messages[-1]
    assert "failure_kind=structured_output_validation" in message
    assert "provider_status_code=unavailable" in message
    assert secret_database_url not in message
