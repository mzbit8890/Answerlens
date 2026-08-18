import asyncio
import ipaddress

import httpx
import pytest

from guardrails.url_safety import URLSafetyValidator
from schemas.crawl import CrawlStatus
from services import crawler
from services.crawler import MAX_CRAWL_PAGES, crawl_website


async def public_resolver(hostname: str, port: int) -> set[ipaddress.IPv4Address]:
    del hostname, port
    return {ipaddress.ip_address("93.184.216.34")}


def run_crawl(
    handler: httpx.AsyncBaseTransport | httpx.MockTransport, *, max_pages: int = 8
):
    async def run():
        async with httpx.AsyncClient(transport=handler) as client:
            return await crawl_website(
                "https://example.com/",
                client=client,
                validator=URLSafetyValidator(public_resolver),
                max_pages=max_pages,
            )

    return asyncio.run(run())


def html_response(request: httpx.Request, body: str, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        headers={"content-type": "text/html; charset=utf-8"},
        text=body,
        request=request,
    )


def test_redirect_to_unsafe_destination_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302, headers={"location": "http://127.0.0.1/private"}, request=request
        )

    result = run_crawl(httpx.MockTransport(handler))

    assert result.pages[0].status is CrawlStatus.FAILED
    assert "non-public address" in (result.pages[0].failure or "")


def test_redirect_outside_company_scope_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302, headers={"location": "https://other.example/about"}, request=request
        )

    result = run_crawl(httpx.MockTransport(handler))

    assert result.pages[0].status is CrawlStatus.FAILED
    assert "outside the target website scope" in (result.pages[0].failure or "")


def test_duplicate_links_are_normalized_and_returned_once() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return html_response(
                request,
                '<a href="/features">One</a><a href="/features/">Two</a>'
                '<a href="https://EXAMPLE.com:443/features#more">Three</a>',
            )
        return html_response(request, "<main>Features</main>")

    result = run_crawl(httpx.MockTransport(handler))

    assert [page.requested_url for page in result.pages] == [
        "https://example.com/",
        "https://example.com/features",
    ]


def test_maximum_page_count_is_enforced() -> None:
    links = "".join(f'<a href="/page-{index}">Page</a>' for index in range(20))

    def handler(request: httpx.Request) -> httpx.Response:
        return html_response(request, links if request.url.path == "/" else "Page")

    result = run_crawl(httpx.MockTransport(handler), max_pages=MAX_CRAWL_PAGES)

    assert len(result.pages) == MAX_CRAWL_PAGES


def test_timeout_is_returned_as_explicit_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    result = run_crawl(httpx.MockTransport(handler))

    assert result.pages[0].status is CrawlStatus.FAILED
    assert result.pages[0].failure == "request timed out"


def test_non_html_response_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/pdf"},
            content=b"not a page",
            request=request,
        )

    result = run_crawl(httpx.MockTransport(handler))

    assert result.pages[0].status is CrawlStatus.FAILED
    assert result.pages[0].failure == "response is not HTML"


def test_oversized_response_is_rejected_from_content_length() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html", "content-length": "2000001"},
            content=b"small test body",
            request=request,
        )

    result = run_crawl(httpx.MockTransport(handler))

    assert result.pages[0].status is CrawlStatus.FAILED
    assert result.pages[0].failure == "response exceeds maximum size"


def test_oversized_streamed_response_is_rejected_without_content_length() -> None:
    class OversizedStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"x" * 1_500_000
            yield b"x" * 500_001

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            stream=OversizedStream(),
            request=request,
        )

    result = run_crawl(httpx.MockTransport(handler))

    assert result.pages[0].status is CrawlStatus.FAILED
    assert result.pages[0].failure == "response exceeds maximum size"


def test_successful_page_preserves_requested_and_final_source_urls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(
                301, headers={"location": "/home"}, request=request
            )
        return html_response(request, "<title>Home</title><main>Evidence</main>")

    result = run_crawl(httpx.MockTransport(handler))
    page = result.pages[0]

    assert page.status is CrawlStatus.SUCCESS
    assert page.requested_url == "https://example.com/"
    assert page.final_url == "https://example.com/home"
    assert page.title == "Home"
    assert page.content == "Evidence"


def test_useful_links_are_prioritized_and_low_value_links_are_skipped() -> None:
    root = """
    <a href="/blog">Blog</a>
    <a href="/privacy-policy">Privacy</a>
    <a href="/pricing">Pricing</a>
    <a href="/login">Login</a>
    <a href="/features">Features</a>
    <a href="/brochure.pdf">PDF</a>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return html_response(request, root if request.url.path == "/" else "Page")

    result = run_crawl(httpx.MockTransport(handler), max_pages=4)

    assert [page.requested_url for page in result.pages] == [
        "https://example.com/",
        "https://example.com/features",
        "https://example.com/pricing",
        "https://example.com/blog",
    ]


def test_low_value_filter_uses_precise_path_segments() -> None:
    excluded = [
        "/login",
        "/sign-in",
        "/signup",
        "/account",
        "/privacy",
        "/privacy-policy",
        "/terms",
        "/terms-of-service",
        "/cookie-policy",
    ]
    legitimate = [
        "/accounting-software",
        "/accounting/features",
        "/long-term-planning",
        "/customer-accounting-platform",
    ]
    root = "".join(f'<a href="{path}">Page</a>' for path in excluded + legitimate)

    def handler(request: httpx.Request) -> httpx.Response:
        return html_response(request, root if request.url.path == "/" else "Page")

    result = run_crawl(httpx.MockTransport(handler), max_pages=5)
    crawled = {page.requested_url for page in result.pages}

    assert {f"https://example.com{path}" for path in legitimate} <= crawled
    assert not {f"https://example.com{path}" for path in excluded} & crawled


def test_owned_client_disables_environment_network_configuration(monkeypatch) -> None:
    captured: dict[str, object] = {}
    sentinel = object()

    def fake_client(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(crawler.httpx, "AsyncClient", fake_client)

    assert crawler.create_crawler_client() is sentinel
    assert captured["trust_env"] is False


def test_failed_child_does_not_discard_successful_pages() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return html_response(
                request, '<a href="/features">Features</a><a href="/pricing">Pricing</a>'
            )
        if request.url.path == "/features":
            raise httpx.ReadTimeout("timed out", request=request)
        return html_response(request, "<main>Pricing evidence</main>")

    result = run_crawl(httpx.MockTransport(handler))

    assert [page.status for page in result.pages] == [
        CrawlStatus.SUCCESS,
        CrawlStatus.FAILED,
        CrawlStatus.SUCCESS,
    ]
    assert result.pages[2].content == "Pricing evidence"
