from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

from guardrails.url_safety import URLSafetyValidator

MAX_REDIRECTS = 5


class SecureFetchFailure(RuntimeError):
    """A bounded, expected failure while safely fetching an external resource."""


@dataclass(frozen=True)
class SecureFetchResult:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    body: bytes


async def _read_limited(response: httpx.Response, limit: int) -> bytes:
    content_length = response.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > limit:
                raise SecureFetchFailure("response exceeds maximum size")
        except ValueError:
            pass

    body = bytearray()
    async for chunk in response.aiter_bytes():
        body.extend(chunk)
        if len(body) > limit:
            raise SecureFetchFailure("response exceeds maximum size")
    return bytes(body)


async def fetch_with_safe_redirects(
    client: httpx.AsyncClient,
    requested_url: str,
    validator: URLSafetyValidator,
    scope: str,
    *,
    max_bytes: int,
) -> SecureFetchResult:
    current_url = requested_url
    for redirect_count in range(MAX_REDIRECTS + 1):
        current_url = await validator.validate(current_url, scope=scope)
        try:
            async with client.stream("GET", current_url, follow_redirects=False) as response:
                if response.is_redirect:
                    if redirect_count == MAX_REDIRECTS:
                        raise SecureFetchFailure("maximum redirect count exceeded")
                    location = response.headers.get("location")
                    if not location:
                        raise SecureFetchFailure("redirect response has no destination")
                    current_url = await validator.validate(
                        urljoin(current_url, location), scope=scope
                    )
                    continue
                body = await _read_limited(response, max_bytes)
                return SecureFetchResult(
                    requested_url=requested_url,
                    final_url=current_url,
                    status_code=response.status_code,
                    content_type=response.headers.get("content-type", ""),
                    body=body,
                )
        except httpx.TimeoutException as exc:
            raise SecureFetchFailure("request timed out") from exc
        except httpx.RequestError as exc:
            raise SecureFetchFailure(f"request failed: {exc}") from exc
    raise SecureFetchFailure("maximum redirect count exceeded")
