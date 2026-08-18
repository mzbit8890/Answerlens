import asyncio
import ipaddress

import httpx
import pytest

from guardrails.url_safety import URLSafetyValidator
from schemas.crawl import CrawlResult
from schemas.machine_readable import ParseStatus, SurfaceStatus
from services.machine_readable import (
    MAX_LLMS_LINKS,
    MAX_LLMS_TXT_BYTES,
    MAX_ROBOTS_BYTES,
    MAX_ROBOTS_SITEMAPS,
    MAX_SITEMAP_DOCUMENTS,
    MAX_SITEMAP_URLS,
    CrawlTargetMismatchError,
    inspect_machine_readable_surfaces,
)


async def public_resolver(hostname: str, port: int) -> set[ipaddress.IPv4Address]:
    del hostname, port
    return {ipaddress.ip_address("93.184.216.34")}


def response(
    request: httpx.Request,
    body: str = "",
    *,
    status: int = 200,
    content_type: str = "text/plain",
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    response_headers = {"content-type": content_type, **(headers or {})}
    return httpx.Response(
        status, text=body, headers=response_headers, request=request
    )


def run_audit(
    handler,
    crawl_result: CrawlResult | None = None,
    *,
    resolver=public_resolver,
    target_url: str = "https://example.com/",
):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await inspect_machine_readable_surfaces(
                target_url,
                crawl_result or CrawlResult(target_url="https://example.com/"),
                client=client,
                validator=URLSafetyValidator(resolver),
            )

    return asyncio.run(run())


def missing_by_default(request: httpx.Request) -> httpx.Response:
    return response(request, status=404)


def test_robots_present_with_rules_and_sitemap_directive() -> None:
    robots = """
    User-agent: AnswerLensCrawler
    Allow: /public
    Disallow: /private
    Sitemap: https://example.com/custom-sitemap.xml
    unusual line without colon
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return response(request, robots)
        if request.url.path == "/custom-sitemap.xml":
            return response(
                request,
                '<urlset><url><loc>https://example.com/product</loc></url></urlset>',
                content_type="application/xml",
            )
        return response(request, status=404)

    audit = run_audit(handler)

    assert audit.robots.status is SurfaceStatus.PRESENT
    assert audit.robots.parse_status is ParseStatus.MALFORMED
    assert audit.robots.malformed_lines == 1
    assert audit.robots.sitemap_urls == ["https://example.com/custom-sitemap.xml"]
    assert {(rule.directive, rule.path) for rule in audit.robots.rules} == {
        ("allow", "/public"),
        ("disallow", "/private"),
    }
    assert audit.sitemap.discovered_urls == ["https://example.com/product"]


def test_robots_missing_is_distinct_from_request_failure() -> None:
    missing = run_audit(missing_by_default)

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            raise httpx.ReadTimeout("timed out", request=request)
        return response(request, status=404)

    unavailable = run_audit(timeout_handler)

    assert missing.robots.status is SurfaceStatus.MISSING
    assert unavailable.robots.status is SurfaceStatus.UNAVAILABLE
    assert unavailable.robots.error == "request timed out"


def test_unsafe_robots_redirect_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return response(
                request,
                status=302,
                headers={"location": "http://127.0.0.1/robots.txt"},
            )
        return response(request, status=404)

    audit = run_audit(handler)

    assert audit.robots.status is SurfaceStatus.UNAVAILABLE
    assert "non-public address" in (audit.robots.error or "")


def test_oversized_robots_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return response(
                request,
                "small",
                headers={"content-length": str(MAX_ROBOTS_BYTES + 1)},
            )
        return response(request, status=404)

    audit = run_audit(handler)

    assert audit.robots.status is SurfaceStatus.UNAVAILABLE
    assert audit.robots.error == "response exceeds maximum size"


def test_unsafe_robots_declared_sitemaps_are_never_fetched() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path == "/robots.txt":
            return response(
                request,
                "Sitemap: http://127.0.0.1/private.xml\n"
                "Sitemap: https://outside.example/sitemap.xml",
            )
        return response(request, status=404)

    audit = run_audit(handler)

    assert audit.sitemap.rejected_urls == [
        "http://127.0.0.1/private.xml",
        "https://outside.example/sitemap.xml",
    ]
    assert requested_paths == ["/robots.txt", "/sitemap.xml", "/llms.txt"]


def test_robots_sitemap_directives_are_bounded() -> None:
    directives = "\n".join(
        f"Sitemap: https://example.com/map-{index}.xml"
        for index in range(MAX_ROBOTS_SITEMAPS + 1)
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return response(request, directives)
        return response(request, status=404)

    audit = run_audit(handler)

    assert len(audit.robots.sitemap_urls) == MAX_ROBOTS_SITEMAPS
    assert audit.robots.sitemap_limit_reached is True


def test_valid_urlset_and_duplicate_url_removal() -> None:
    xml = """
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/product</loc></url>
      <url><loc>https://example.com/product/</loc></url>
      <url><loc>https://example.com/pricing</loc></url>
    </urlset>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/sitemap.xml":
            return response(request, xml, content_type="application/xml")
        return response(request, status=404)

    audit = run_audit(handler)

    assert audit.sitemap.status is SurfaceStatus.PRESENT
    assert audit.sitemap.documents[0].kind == "urlset"
    assert audit.sitemap.discovered_urls == [
        "https://example.com/product",
        "https://example.com/pricing",
    ]


def test_sitemapindex_is_followed_within_document_limit() -> None:
    index = """
    <sitemapindex>
      <sitemap><loc>https://example.com/one.xml</loc></sitemap>
      <sitemap><loc>https://example.com/two.xml</loc></sitemap>
    </sitemapindex>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/sitemap.xml":
            return response(request, index, content_type="application/xml")
        if request.url.path.endswith(".xml"):
            page = request.url.path.removesuffix(".xml").removeprefix("/")
            return response(
                request,
                f"<urlset><url><loc>https://example.com/{page}</loc></url></urlset>",
                content_type="application/xml",
            )
        return response(request, status=404)

    audit = run_audit(handler)

    assert len(audit.sitemap.documents) == 3
    assert audit.sitemap.discovered_urls == [
        "https://example.com/one",
        "https://example.com/two",
    ]


def test_sitemap_rejects_unsafe_and_out_of_scope_urls() -> None:
    xml = """
    <urlset>
      <url><loc>http://127.0.0.1/admin</loc></url>
      <url><loc>https://outside.example/page</loc></url>
      <url><loc>https://example.com/safe</loc></url>
    </urlset>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/sitemap.xml":
            return response(request, xml, content_type="application/xml")
        return response(request, status=404)

    audit = run_audit(handler)

    assert audit.sitemap.discovered_urls == ["https://example.com/safe"]
    assert audit.sitemap.rejected_urls == [
        "http://127.0.0.1/admin",
        "https://outside.example/page",
    ]


def test_non_fetched_sitemap_page_references_do_not_resolve_dns() -> None:
    resolved_hosts: list[str] = []

    async def recording_resolver(hostname: str, port: int):
        del port
        resolved_hosts.append(hostname)
        return {ipaddress.ip_address("93.184.216.34")}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/sitemap.xml":
            return response(
                request,
                "<urlset><url><loc>https://pages.example.com/product</loc></url></urlset>",
                content_type="application/xml",
            )
        return response(request, status=404)

    audit = run_audit(handler, resolver=recording_resolver)

    assert audit.sitemap.discovered_urls == ["https://pages.example.com/product"]
    assert "pages.example.com" not in resolved_hosts


def test_sitemap_documents_that_are_fetched_still_use_full_dns_validation() -> None:
    resolved_hosts: list[str] = []

    async def recording_resolver(hostname: str, port: int):
        del port
        resolved_hosts.append(hostname)
        return {ipaddress.ip_address("93.184.216.34")}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return response(
                request, "Sitemap: https://maps.example.com/company.xml"
            )
        if request.url.path == "/company.xml":
            return response(request, "<urlset />", content_type="application/xml")
        return response(request, status=404)

    audit = run_audit(handler, resolver=recording_resolver)

    assert any(
        document.source_url == "https://maps.example.com/company.xml"
        and document.status is SurfaceStatus.PRESENT
        for document in audit.sitemap.documents
    )
    assert "maps.example.com" in resolved_hosts


def test_malformed_and_oversized_sitemaps_have_explicit_states() -> None:
    def malformed_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/sitemap.xml":
            return response(request, "<urlset><url>", content_type="application/xml")
        return response(request, status=404)

    malformed = run_audit(malformed_handler)

    def oversized_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/sitemap.xml":
            return response(
                request,
                "small",
                content_type="application/xml",
                headers={"content-length": "2000001"},
            )
        return response(request, status=404)

    oversized = run_audit(oversized_handler)

    assert malformed.sitemap.status is SurfaceStatus.MALFORMED
    assert oversized.sitemap.status is SurfaceStatus.UNAVAILABLE
    assert oversized.sitemap.documents[0].error == "response exceeds maximum size"


def test_sitemap_xml_entity_expansion_is_rejected_as_malformed() -> None:
    hostile_xml = """
    <!DOCTYPE urlset [<!ENTITY x "expanded">]>
    <urlset><url><loc>https://example.com/&x;</loc></url></urlset>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/sitemap.xml":
            return response(request, hostile_xml, content_type="application/xml")
        return response(request, status=404)

    audit = run_audit(handler)

    assert audit.sitemap.status is SurfaceStatus.MALFORMED
    assert "invalid sitemap XML" in (audit.sitemap.documents[0].error or "")


def test_sitemap_document_limit_is_enforced() -> None:
    children = "".join(
        f"<sitemap><loc>https://example.com/{index}.xml</loc></sitemap>"
        for index in range(10)
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/sitemap.xml":
            return response(
                request,
                f"<sitemapindex>{children}</sitemapindex>",
                content_type="application/xml",
            )
        if request.url.path.endswith(".xml"):
            return response(request, "<urlset />", content_type="application/xml")
        return response(request, status=404)

    audit = run_audit(handler)

    assert len(audit.sitemap.documents) == MAX_SITEMAP_DOCUMENTS
    assert audit.sitemap.document_limit_reached is True


def test_sitemap_retained_url_limit_is_enforced() -> None:
    urls = "".join(
        f"<url><loc>https://example.com/page-{index}</loc></url>"
        for index in range(MAX_SITEMAP_URLS + 1)
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/sitemap.xml":
            return response(
                request, f"<urlset>{urls}</urlset>", content_type="application/xml"
            )
        return response(request, status=404)

    audit = run_audit(handler)

    assert len(audit.sitemap.discovered_urls) == MAX_SITEMAP_URLS
    assert audit.sitemap.url_limit_reached is True


def test_llms_txt_present_extracts_title_summary_and_classified_unique_links() -> None:
    text = """
    # Example Product
    > A concise publisher-provided summary.
    > It remains unverified.

    - [Docs](/docs)
    - [Duplicate docs](https://example.com/docs/)
    - [External](https://external.example/resource)
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/llms.txt":
            return response(request, text)
        return response(request, status=404)

    audit = run_audit(handler)

    assert audit.llms_txt.status is SurfaceStatus.PRESENT
    assert audit.llms_txt.title == "Example Product"
    assert audit.llms_txt.summary == (
        "A concise publisher-provided summary. It remains unverified."
    )
    assert [(link.url, link.internal) for link in audit.llms_txt.links] == [
        ("https://example.com/docs", True),
        ("https://external.example/resource", False),
    ]


def test_non_fetched_llms_links_do_not_resolve_dns() -> None:
    resolved_hosts: list[str] = []

    async def recording_resolver(hostname: str, port: int):
        del port
        resolved_hosts.append(hostname)
        return {ipaddress.ip_address("93.184.216.34")}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/llms.txt":
            return response(
                request,
                "[Internal](https://docs.example.com/guide)\n"
                "[External](https://publisher.example/resource)",
            )
        return response(request, status=404)

    audit = run_audit(handler, resolver=recording_resolver)

    assert len(audit.llms_txt.links) == 2
    assert "docs.example.com" not in resolved_hosts
    assert "publisher.example" not in resolved_hosts


def test_llms_rejects_malformed_local_credential_and_private_references() -> None:
    text = """
    [Malformed](ftp://example.com/file)
    [Credentials](https://user:secret@example.com/private)
    [Local](http://localhost/admin)
    [Private](http://10.0.0.5/admin)
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/llms.txt":
            return response(request, text)
        return response(request, status=404)

    audit = run_audit(handler)

    assert audit.llms_txt.links == []
    assert audit.llms_txt.rejected_links == [
        "ftp://example.com/file",
        "https://user:secret@example.com/private",
        "http://localhost/admin",
        "http://10.0.0.5/admin",
    ]


def test_llms_txt_missing_is_optional_and_does_not_fail_audit() -> None:
    audit = run_audit(missing_by_default)

    assert audit.llms_txt.status is SurfaceStatus.MISSING
    assert audit.summary.llms_txt_links_discovered == 0


def test_oversized_llms_txt_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/llms.txt":
            return response(
                request,
                "small",
                headers={"content-length": str(MAX_LLMS_TXT_BYTES + 1)},
            )
        return response(request, status=404)

    audit = run_audit(handler)

    assert audit.llms_txt.status is SurfaceStatus.UNAVAILABLE
    assert audit.llms_txt.error == "response exceeds maximum size"


def test_llms_txt_link_count_is_bounded() -> None:
    links = "\n".join(
        f"- [Resource](https://external.example/resource-{index})"
        for index in range(MAX_LLMS_LINKS + 1)
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/llms.txt":
            return response(request, links)
        return response(request, status=404)

    audit = run_audit(handler)

    assert len(audit.llms_txt.links) == MAX_LLMS_LINKS
    assert audit.llms_txt.link_limit_reached is True


def test_surface_failures_are_independent() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return response(request, "User-agent: *\nAllow: /")
        if request.url.path == "/sitemap.xml":
            return response(request, "not xml", content_type="application/xml")
        return response(request, status=404)

    audit = run_audit(handler)

    assert audit.robots.status is SurfaceStatus.PRESENT
    assert audit.sitemap.status is SurfaceStatus.MALFORMED
    assert audit.llms_txt.status is SurfaceStatus.MISSING


def test_matching_and_www_crawl_targets_are_accepted() -> None:
    matching = run_audit(
        missing_by_default,
        CrawlResult(target_url="https://example.com/"),
    )
    www = run_audit(
        missing_by_default,
        CrawlResult(target_url="https://www.example.com/"),
    )

    assert matching.target_url == "https://example.com/"
    assert www.target_url == "https://example.com/"


def test_different_website_crawl_result_is_rejected_explicitly() -> None:
    mismatched = CrawlResult(target_url="https://company-b.example/")

    with pytest.raises(CrawlTargetMismatchError, match="outside the audited target scope"):
        run_audit(missing_by_default, mismatched)
