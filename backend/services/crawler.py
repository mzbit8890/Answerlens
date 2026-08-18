import heapq
import itertools
from urllib.parse import urljoin, urlsplit

import httpx

from guardrails.network_safety import PinnedAsyncHTTPTransport
from guardrails.url_safety import (
    URLSafetyError,
    URLSafetyValidator,
    company_scope,
    is_within_scope,
    normalize_url,
)
from schemas.crawl import CrawledPage, CrawlResult, CrawlStatus
from services.html_extractor import extract_html
from services.secure_fetch import (
    MAX_REDIRECTS,
    SecureFetchFailure,
    fetch_with_safe_redirects,
)

MAX_CRAWL_PAGES = 8
REQUEST_TIMEOUT_SECONDS = 10.0
MAX_RESPONSE_BYTES = 2_000_000

_USEFUL_TERMS = (
    "product",
    "features",
    "pricing",
    "about",
    "docs",
    "documentation",
    "faq",
    "use-case",
    "use_cases",
    "customers",
    "customer-stories",
    "case-studies",
)
_LOW_VALUE_SEGMENTS = {
    "login",
    "log-in",
    "signin",
    "sign-in",
    "signup",
    "sign-up",
    "account",
    "privacy",
    "privacy-policy",
    "terms",
    "terms-of-service",
    "cookie",
    "cookie-policy",
}
_BLOCKED_EXTENSIONS = (
    ".7z", ".avi", ".css", ".csv", ".doc", ".docx", ".gif", ".gz", ".ico",
    ".jpeg", ".jpg", ".js", ".json", ".mov", ".mp3", ".mp4", ".pdf", ".png",
    ".ppt", ".pptx", ".rar", ".svg", ".tar", ".txt", ".webm", ".webp", ".xls",
    ".xlsx", ".xml", ".zip",
)


class CrawlFailure(SecureFetchFailure):
    """A bounded, expected failure while fetching an individual page."""


def _priority(url: str, root_url: str) -> int:
    if url == root_url:
        return -100
    path = urlsplit(url).path.lower()
    for index, term in enumerate(_USEFUL_TERMS):
        if term in path:
            return index
    return 100


def _is_low_value(url: str) -> bool:
    path = urlsplit(url).path.lower()
    segments = {segment for segment in path.split("/") if segment}
    return bool(segments & _LOW_VALUE_SEGMENTS) or path.endswith(_BLOCKED_EXTENSIONS)


def _is_html(content_type: str) -> bool:
    media_type = content_type.split(";", 1)[0].strip().lower()
    return media_type in {"text/html", "application/xhtml+xml"}


async def _request_with_safe_redirects(
    client: httpx.AsyncClient,
    requested_url: str,
    validator: URLSafetyValidator,
    scope: str,
) -> tuple[httpx.Response, bytes, str]:
    try:
        fetched = await fetch_with_safe_redirects(
            client,
            requested_url,
            validator,
            scope,
            max_bytes=MAX_RESPONSE_BYTES,
        )
    except SecureFetchFailure as exc:
        raise CrawlFailure(str(exc)) from exc
    if not 200 <= fetched.status_code < 300:
        raise CrawlFailure(f"HTTP request returned status {fetched.status_code}")
    if not _is_html(fetched.content_type):
        raise CrawlFailure("response is not HTML")
    response = httpx.Response(fetched.status_code, request=httpx.Request("GET", fetched.final_url))
    return response, fetched.body, fetched.final_url


def _internal_links(links: list[str], base_url: str, scope: str) -> list[str]:
    normalized_links: set[str] = set()
    for link in links:
        if not link or link.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
            continue
        try:
            normalized = normalize_url(urljoin(base_url, link))
        except URLSafetyError:
            continue
        hostname = urlsplit(normalized).hostname
        if hostname and is_within_scope(hostname, scope) and not _is_low_value(normalized):
            normalized_links.add(normalized)
    return sorted(normalized_links, key=lambda url: (_priority(url, base_url), url))


def create_crawler_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS),
        headers={"User-Agent": "AnswerLensCrawler/1.0"},
        transport=PinnedAsyncHTTPTransport(),
        trust_env=False,
    )


_create_crawler_client = create_crawler_client


async def crawl_website(
    target_url: str,
    *,
    client: httpx.AsyncClient | None = None,
    validator: URLSafetyValidator | None = None,
    max_pages: int = MAX_CRAWL_PAGES,
) -> CrawlResult:
    if max_pages < 1 or max_pages > MAX_CRAWL_PAGES:
        raise ValueError(f"max_pages must be between 1 and {MAX_CRAWL_PAGES}")

    safety = validator or URLSafetyValidator()
    root_url = await safety.validate(target_url)
    root_host = urlsplit(root_url).hostname
    assert root_host is not None
    scope = company_scope(root_host)

    owns_client = client is None
    http_client = client or create_crawler_client()
    queue: list[tuple[int, int, str]] = []
    sequence = itertools.count()
    heapq.heappush(queue, (_priority(root_url, root_url), next(sequence), root_url))
    queued = {root_url}
    visited: set[str] = set()
    pages: list[CrawledPage] = []

    try:
        while queue and len(pages) < max_pages:
            _, _, requested_url = heapq.heappop(queue)
            if requested_url in visited:
                continue
            visited.add(requested_url)

            try:
                _, body, final_url = await _request_with_safe_redirects(
                    http_client, requested_url, safety, scope
                )
                extracted = extract_html(body.decode("utf-8", errors="replace"))
                internal_links = _internal_links(extracted.links, final_url, scope)
                page = CrawledPage(
                    requested_url=requested_url,
                    final_url=final_url,
                    status=CrawlStatus.SUCCESS,
                    title=extracted.title,
                    meta_description=extracted.meta_description,
                    headings=extracted.headings,
                    content=extracted.content,
                    internal_links=internal_links,
                    json_ld=extracted.json_ld,
                )
                for link in internal_links:
                    if link not in queued and link not in visited:
                        queued.add(link)
                        heapq.heappush(
                            queue, (_priority(link, root_url), next(sequence), link)
                        )
            except (CrawlFailure, URLSafetyError) as exc:
                page = CrawledPage(
                    requested_url=requested_url,
                    status=CrawlStatus.FAILED,
                    failure=str(exc),
                )
            pages.append(page)
    finally:
        if owns_client:
            await http_client.aclose()

    return CrawlResult(target_url=root_url, pages=pages)
