import logging
import os
import re
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar

from pydantic import ValidationError

from providers.gemini import GeminiRequestError, GeminiStructuredOutputError

logger = logging.getLogger("answerlens.workflow")
T = TypeVar("T")
MAX_DIAGNOSTIC_MESSAGE_LENGTH = 800
SEMANTIC_ERROR_NAMES = {
    "BrandIntelligenceError",
    "ClaimEvidenceMappingError",
    "EvidenceGapError",
    "GeoExperimentError",
    "QueryEvaluationError",
    "TargetedResearchError",
}


def _cause_chain(exc: BaseException) -> list[BaseException]:
    chain = [exc]
    seen = {id(exc)}
    current = exc
    while current.__cause__ is not None and id(current.__cause__) not in seen:
        current = current.__cause__
        seen.add(id(current))
        chain.append(current)
    return chain


def _sanitize_message(message: str) -> str:
    sanitized = message
    for name in ("GEMINI_API_KEY", "TAVILY_API_KEY", "DATABASE_URL"):
        secret = os.getenv(name)
        if secret:
            sanitized = sanitized.replace(secret, "[REDACTED]")
    sanitized = re.sub(
        r"(?i)(postgres(?:ql)?://)[^\s/@:]+(?::[^\s/@]*)?@",
        r"\1[REDACTED]@",
        sanitized,
    )
    return " ".join(sanitized.split())[:MAX_DIAGNOSTIC_MESSAGE_LENGTH]


def provider_status_code(exc: BaseException) -> int | None:
    chain = _cause_chain(exc)
    for item in chain:
        for candidate in (
            getattr(item, "status_code", None),
            getattr(item, "code", None),
            getattr(getattr(item, "response", None), "status_code", None),
        ):
            if isinstance(candidate, int) and 100 <= candidate <= 599:
                return candidate
    return None


def _failure_kind(exc: BaseException, chain: list[BaseException]) -> str:
    if isinstance(exc, GeminiRequestError):
        return "provider_request"
    if isinstance(exc, GeminiStructuredOutputError) or any(
        isinstance(item, (ValidationError, ValueError)) for item in chain[1:]
    ):
        return "structured_output_validation"
    if exc.__class__.__name__ in SEMANTIC_ERROR_NAMES:
        return "application_semantic_validation"
    return "workflow_stage"


def log_workflow_failure(stage: str, exc: BaseException) -> None:
    chain = _cause_chain(exc)
    root = chain[-1]
    status_code = provider_status_code(exc)
    logger.error(
        "AnswerLens workflow failure stage=%s failure_kind=%s "
        "exception_class=%s cause_class=%s provider_status_code=%s message=%s",
        stage,
        _failure_kind(exc, chain),
        exc.__class__.__name__,
        root.__class__.__name__,
        status_code if status_code is not None else "unavailable",
        _sanitize_message(str(root) or str(exc) or "no exception message"),
    )


def diagnostic_node(
    stage: str,
    function: Callable[..., Awaitable[T]],
) -> Callable[..., Awaitable[T]]:
    @wraps(function)
    async def wrapped(*args: Any, **kwargs: Any) -> T:
        try:
            return await function(*args, **kwargs)
        except Exception as exc:
            log_workflow_failure(stage, exc)
            raise

    return wrapped
