import os
from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from providers.base import OutputModelT

GEMINI_MODEL = "gemini-3.6-flash"
MAX_STRUCTURED_OUTPUT_ATTEMPTS = 2


class GeminiProviderError(RuntimeError):
    """Base error for the Gemini structured-output provider."""


class GeminiConfigurationError(GeminiProviderError):
    """The real Gemini client cannot be configured safely."""


class GeminiRequestError(GeminiProviderError):
    """The Gemini API request failed before usable output was returned."""


class GeminiStructuredOutputError(GeminiProviderError):
    """Gemini output remained invalid after the bounded attempts."""


def _gemini_compatible_schema(value: Any) -> Any:
    """Remove JSON Schema keywords unsupported by Gemini's response schema API."""
    if isinstance(value, dict):
        return {
            key: _gemini_compatible_schema(item)
            for key, item in value.items()
            if key != "additionalProperties"
        }
    if isinstance(value, list):
        return [_gemini_compatible_schema(item) for item in value]
    return value


class GeminiStructuredOutputProvider:
    def __init__(self, *, client: Any | None = None) -> None:
        if client is not None:
            self._client = client
            return

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise GeminiConfigurationError(
                "GEMINI_API_KEY is required to construct the Gemini provider"
            )
        try:
            self._client = genai.Client(api_key=api_key)
        except Exception as exc:
            raise GeminiConfigurationError(
                "Gemini client configuration failed"
            ) from exc

    async def generate_structured(
        self,
        prompt: str,
        response_model: type[OutputModelT],
    ) -> OutputModelT:
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=_gemini_compatible_schema(
                response_model.model_json_schema()
            ),
        )
        last_output_error: ValueError | ValidationError | None = None

        for _ in range(MAX_STRUCTURED_OUTPUT_ATTEMPTS):
            try:
                response = await self._client.aio.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                    config=config,
                )
            except Exception as exc:
                raise GeminiRequestError(
                    "Gemini structured-output request failed"
                ) from exc

            try:
                response_text = response.text
                if not isinstance(response_text, str) or not response_text.strip():
                    raise ValueError("Gemini returned empty structured output")
                return response_model.model_validate_json(response_text)
            except (ValidationError, ValueError) as exc:
                last_output_error = exc

        raise GeminiStructuredOutputError(
            f"Gemini returned invalid structured output after "
            f"{MAX_STRUCTURED_OUTPUT_ATTEMPTS} attempts"
        ) from last_output_error
