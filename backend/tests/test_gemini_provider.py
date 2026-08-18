import asyncio
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from providers.base import StructuredOutputProvider
from providers.gemini import (
    GEMINI_MODEL,
    MAX_STRUCTURED_OUTPUT_ATTEMPTS,
    GeminiConfigurationError,
    GeminiRequestError,
    GeminiStructuredOutputError,
    GeminiStructuredOutputProvider,
)
from schemas.brand import BrandProfile


class StructuredTestOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    count: int


class FakeModels:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, object]] = []

    async def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(text=outcome)


class FakeClient:
    def __init__(self, outcomes: list[object]) -> None:
        self.models = FakeModels(outcomes)
        self.aio = SimpleNamespace(models=self.models)


def generate(provider, model=StructuredTestOutput):
    return asyncio.run(
        provider.generate_structured(
            "Return the requested structured test object.", model
        )
    )


def test_successful_response_returns_requested_pydantic_model() -> None:
    provider = GeminiStructuredOutputProvider(
        client=FakeClient(['{"name":"Example","count":2}'])
    )

    result = generate(provider)

    assert isinstance(result, StructuredTestOutput)
    assert result == StructuredTestOutput(name="Example", count=2)


def test_brand_profile_is_supported_as_response_contract() -> None:
    provider = GeminiStructuredOutputProvider(
        client=FakeClient(
            [
                '{"brand":"Example","category":null,"audiences":[],"capabilities":[],'
                '"use_cases":[],"positioning":null,"claims":[]}'
            ]
        )
    )

    result = generate(provider, BrandProfile)

    assert isinstance(result, BrandProfile)
    assert result.brand == "Example"


def test_request_uses_configured_model_json_mime_and_requested_schema() -> None:
    client = FakeClient(['{"name":"Example","count":2}'])
    provider = GeminiStructuredOutputProvider(client=client)

    generate(provider)

    call = client.models.calls[0]
    assert call["model"] == GEMINI_MODEL == "gemini-2.5-flash"
    assert call["contents"] == "Return the requested structured test object."
    config = call["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_schema is StructuredTestOutput


@pytest.mark.parametrize(
    "invalid_output",
    [
        '{"name":',
        '{"name":"Example","count":"not-an-integer"}',
        '{"name":"Example","count":2,"unexpected":true}',
        "",
        "   ",
    ],
)
def test_invalid_output_fails_after_bounded_attempts(invalid_output: str) -> None:
    client = FakeClient([invalid_output] * MAX_STRUCTURED_OUTPUT_ATTEMPTS)
    provider = GeminiStructuredOutputProvider(client=client)

    with pytest.raises(GeminiStructuredOutputError, match="after 2 attempts"):
        generate(provider)

    assert len(client.models.calls) == MAX_STRUCTURED_OUTPUT_ATTEMPTS


def test_malformed_first_response_then_valid_second_response_succeeds() -> None:
    client = FakeClient(['{"name":', '{"name":"Recovered","count":1}'])
    provider = GeminiStructuredOutputProvider(client=client)

    result = generate(provider)

    assert result == StructuredTestOutput(name="Recovered", count=1)
    assert len(client.models.calls) == 2


def test_api_failure_is_exposed_without_retry_or_secret_text() -> None:
    secret = "super-secret-api-key"
    client = FakeClient([RuntimeError(f"upstream failed with {secret}")])
    provider = GeminiStructuredOutputProvider(client=client)

    with pytest.raises(GeminiRequestError) as raised:
        generate(provider)

    assert len(client.models.calls) == 1
    assert secret not in str(raised.value)
    assert isinstance(raised.value.__cause__, RuntimeError)


def test_injected_client_requires_no_environment_key(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    provider: StructuredOutputProvider = GeminiStructuredOutputProvider(
        client=FakeClient(['{"name":"Example","count":2}'])
    )

    assert generate(provider) == StructuredTestOutput(name="Example", count=2)


def test_real_provider_construction_requires_environment_key(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(GeminiConfigurationError, match="GEMINI_API_KEY is required"):
        GeminiStructuredOutputProvider()


def test_configuration_failure_is_not_retried_and_does_not_expose_key(
    monkeypatch,
) -> None:
    secret = "configuration-secret"
    calls = 0

    def failing_client(*, api_key: str):
        nonlocal calls
        calls += 1
        assert api_key == secret
        raise RuntimeError(f"invalid key: {api_key}")

    monkeypatch.setenv("GEMINI_API_KEY", secret)
    monkeypatch.setattr("providers.gemini.genai.Client", failing_client)

    with pytest.raises(GeminiConfigurationError) as raised:
        GeminiStructuredOutputProvider()

    assert calls == 1
    assert secret not in str(raised.value)


def test_schema_validation_cause_is_preserved() -> None:
    provider = GeminiStructuredOutputProvider(
        client=FakeClient(['{"name":"Example"}', '{"name":"Example"}'])
    )

    with pytest.raises(GeminiStructuredOutputError) as raised:
        generate(provider)

    assert isinstance(raised.value.__cause__, ValidationError)
