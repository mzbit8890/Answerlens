import asyncio

import pytest

from providers.search import (
    SearchConfigurationError,
    SearchRequestError,
)
from providers.tavily import TavilySearchProvider


class FakeClient:
    def __init__(
        self,
        response=None,
        error=None,
    ):
        self.response = (
            {"results": []}
            if response is None
            else response
        )
        self.error = error
        self.calls = []

    async def search(self, **kwargs):
        self.calls.append(kwargs)

        if self.error:
            raise self.error

        return self.response


def test_real_provider_requires_environment_key(
    monkeypatch,
):
    monkeypatch.delenv(
        "TAVILY_API_KEY",
        raising=False,
    )

    with pytest.raises(
        SearchConfigurationError,
        match="TAVILY_API_KEY",
    ):
        TavilySearchProvider()


def test_injected_client_needs_no_key_and_uses_bounded_configuration(
    monkeypatch,
):
    monkeypatch.delenv(
        "TAVILY_API_KEY",
        raising=False,
    )

    client = FakeClient(
        {
            "results": [
                {
                    "url": "https://example.org",
                    "title": "Title",
                    "content": "Text",
                    "score": 0.7,
                }
            ]
        }
    )

    provider = TavilySearchProvider(
        client=client
    )

    results = asyncio.run(
        provider.search(
            "query",
            max_results=100,
        )
    )

    assert len(results) == 1

    assert client.calls == [
        {
            "query": "query",
            "topic": "general",
            "search_depth": "basic",
            "max_results": 5,
            "include_answer": False,
            "include_raw_content": False,
            "auto_parameters": False,
        }
    ]


def test_request_failure_is_explicit_and_does_not_expose_secret():
    secret = "tvly-secret-value"

    provider = TavilySearchProvider(
        client=FakeClient(
            error=RuntimeError(secret)
        )
    )

    with pytest.raises(
        SearchRequestError
    ) as raised:
        asyncio.run(
            provider.search(
                "query",
                max_results=5,
            )
        )

    assert secret not in str(
        raised.value
    )

    assert isinstance(
        raised.value.__cause__,
        RuntimeError,
    )


def test_malformed_tavily_response_is_request_failure():
    provider = TavilySearchProvider(
        client=FakeClient(
            response="invalid"
        )
    )

    with pytest.raises(
        SearchRequestError,
        match="invalid response",
    ):
        asyncio.run(
            provider.search(
                "query",
                max_results=5,
            )
        )


def test_missing_results_payload_is_request_failure():
    provider = TavilySearchProvider(
        client=FakeClient(
            response={"unexpected": []}
        )
    )

    with pytest.raises(
        SearchRequestError,
        match="invalid results payload",
    ):
        asyncio.run(
            provider.search(
                "query",
                max_results=5,
            )
        )


def test_valid_empty_results_are_successful():
    provider = TavilySearchProvider(
        client=FakeClient(
            response={"results": []}
        )
    )

    results = asyncio.run(
        provider.search(
            "query",
            max_results=5,
        )
    )

    assert results == []