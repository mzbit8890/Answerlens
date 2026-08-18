import re
from collections import deque
from collections.abc import Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from defusedxml.ElementTree import fromstring
from defusedxml.common import DefusedXmlException

from guardrails.url_safety import (
    URLSafetyError,
    URLSafetyValidator,
    company_scope,
    is_within_scope,
    normalize_url,
    validate_url_reference,
)
from schemas.crawl import CrawlResult, CrawlStatus
from schemas.machine_readable import (
    LlmsLink,
    LlmsTxtInspection,
    MachineReadableAudit,
    MachineReadableSummary,
    MalformedStructuredData,
    ParseStatus,
    RobotsInspection,
    RobotsRule,
    SitemapDocument,
    SitemapInspection,
    StructuredDataInspection,
    StructuredDataItem,
    SurfaceStatus,
)
from services.crawler import create_crawler_client
from services.secure_fetch import SecureFetchFailure, fetch_with_safe_redirects

MAX_ROBOTS_BYTES = 256_000
MAX_ROBOTS_SITEMAPS = 10
MAX_SITEMAP_BYTES = 2_000_000
MAX_SITEMAP_DOCUMENTS = 5
MAX_SITEMAP_URLS = 500
MAX_LLMS_TXT_BYTES = 512_000
MAX_LLMS_LINKS = 100
MAX_STRUCTURED_DATA_ITEMS = 500
MAX_STRUCTURED_DATA_DEPTH = 20
MAX_STRUCTURED_DATA_NODES = 5_000

_MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)")


def _origin_url(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, "/", "", ""))


def _surface_status(status_code: int) -> SurfaceStatus:
    if status_code in {404, 410}:
        return SurfaceStatus.MISSING
    if 200 <= status_code < 300:
        return SurfaceStatus.PRESENT
    return SurfaceStatus.UNAVAILABLE


async def _inspect_robots(
    source_url: str,
    client: httpx.AsyncClient,
    validator: URLSafetyValidator,
    scope: str,
) -> RobotsInspection:
    try:
        fetched = await fetch_with_safe_redirects(
            client, source_url, validator, scope, max_bytes=MAX_ROBOTS_BYTES
        )
    except (SecureFetchFailure, URLSafetyError) as exc:
        return RobotsInspection(
            source_url=source_url, status=SurfaceStatus.UNAVAILABLE, error=str(exc)
        )

    status = _surface_status(fetched.status_code)
    if status is not SurfaceStatus.PRESENT:
        return RobotsInspection(
            source_url=source_url,
            final_url=fetched.final_url,
            status=status,
            error=(
                None
                if status is SurfaceStatus.MISSING
                else f"HTTP request returned status {fetched.status_code}"
            ),
        )

    raw_text = fetched.body.decode("utf-8", errors="replace")
    sitemap_urls: list[str] = []
    sitemap_limit_reached = False
    rules: list[RobotsRule] = []
    malformed_lines = 0
    current_agents: list[str] = []
    rules_started = False
    for original_line in raw_text.splitlines():
        line = original_line.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            malformed_lines += 1
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        lowered_key = key.lower()
        if lowered_key == "user-agent":
            if rules_started:
                current_agents = []
                rules_started = False
            if value:
                current_agents.append(value)
            else:
                malformed_lines += 1
        elif lowered_key in {"allow", "disallow"}:
            if not current_agents:
                malformed_lines += 1
                continue
            rules_started = True
            for agent in current_agents:
                rules.append(
                    RobotsRule(user_agent=agent, directive=lowered_key, path=value)
                )
        elif lowered_key == "sitemap":
            if value and value not in sitemap_urls:
                if len(sitemap_urls) < MAX_ROBOTS_SITEMAPS:
                    sitemap_urls.append(value)
                else:
                    sitemap_limit_reached = True
            elif not value:
                malformed_lines += 1

    return RobotsInspection(
        source_url=source_url,
        final_url=fetched.final_url,
        status=SurfaceStatus.PRESENT,
        parse_status=(
            ParseStatus.MALFORMED if malformed_lines else ParseStatus.PARSED
        ),
        raw_text=raw_text,
        sitemap_urls=sitemap_urls,
        sitemap_limit_reached=sitemap_limit_reached,
        rules=rules,
        malformed_lines=malformed_lines,
    )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _loc_values(root: object, parent_name: str) -> Iterable[str]:
    for element in root:  # type: ignore[union-attr]
        if _local_name(element.tag) != parent_name:
            continue
        for child in element:
            if _local_name(child.tag) == "loc" and child.text and child.text.strip():
                yield child.text.strip()


def _aggregate_sitemap_status(documents: list[SitemapDocument]) -> SurfaceStatus:
    statuses = {document.status for document in documents}
    if SurfaceStatus.PRESENT in statuses:
        return SurfaceStatus.PRESENT
    if SurfaceStatus.MALFORMED in statuses:
        return SurfaceStatus.MALFORMED
    if SurfaceStatus.UNAVAILABLE in statuses:
        return SurfaceStatus.UNAVAILABLE
    return SurfaceStatus.MISSING


async def _inspect_sitemaps(
    default_url: str,
    declared_urls: list[str],
    client: httpx.AsyncClient,
    validator: URLSafetyValidator,
    scope: str,
) -> SitemapInspection:
    queue: deque[str] = deque([default_url, *declared_urls])
    queued: set[str] = set()
    documents: list[SitemapDocument] = []
    discovered_urls: list[str] = []
    discovered_set: set[str] = set()
    rejected_urls: list[str] = []
    url_limit_reached = False
    document_limit_reached = len(queue) > MAX_SITEMAP_DOCUMENTS

    while queue and len(documents) < MAX_SITEMAP_DOCUMENTS:
        raw_document_url = queue.popleft()
        try:
            document_url = normalize_url(urljoin(default_url, raw_document_url))
        except URLSafetyError as exc:
            rejected_urls.append(raw_document_url)
            documents.append(
                SitemapDocument(
                    source_url=raw_document_url,
                    status=SurfaceStatus.UNAVAILABLE,
                    error=str(exc),
                )
            )
            continue
        if document_url in queued:
            continue
        queued.add(document_url)
        try:
            document_url = await validator.validate(document_url, scope=scope)
            fetched = await fetch_with_safe_redirects(
                client,
                document_url,
                validator,
                scope,
                max_bytes=MAX_SITEMAP_BYTES,
            )
        except (SecureFetchFailure, URLSafetyError) as exc:
            rejected_urls.append(document_url)
            documents.append(
                SitemapDocument(
                    source_url=document_url,
                    status=SurfaceStatus.UNAVAILABLE,
                    error=str(exc),
                )
            )
            continue

        status = _surface_status(fetched.status_code)
        if status is not SurfaceStatus.PRESENT:
            documents.append(
                SitemapDocument(
                    source_url=document_url,
                    final_url=fetched.final_url,
                    status=status,
                    error=(
                        None
                        if status is SurfaceStatus.MISSING
                        else f"HTTP request returned status {fetched.status_code}"
                    ),
                )
            )
            continue
        try:
            root = fromstring(fetched.body)
        except (DefusedXmlException, SyntaxError, ValueError) as exc:
            documents.append(
                SitemapDocument(
                    source_url=document_url,
                    final_url=fetched.final_url,
                    status=SurfaceStatus.MALFORMED,
                    error=f"invalid sitemap XML: {exc}",
                )
            )
            continue

        kind = _local_name(root.tag)
        if kind not in {"urlset", "sitemapindex"}:
            documents.append(
                SitemapDocument(
                    source_url=document_url,
                    final_url=fetched.final_url,
                    status=SurfaceStatus.MALFORMED,
                    error=f"unsupported sitemap root element: {kind}",
                )
            )
            continue
        documents.append(
            SitemapDocument(
                source_url=document_url,
                final_url=fetched.final_url,
                status=SurfaceStatus.PRESENT,
                kind=kind,
            )
        )

        if kind == "sitemapindex":
            for child_url in _loc_values(root, "sitemap"):
                if child_url not in queue and child_url not in queued:
                    if len(documents) + len(queue) >= MAX_SITEMAP_DOCUMENTS:
                        document_limit_reached = True
                        break
                    queue.append(child_url)
            continue

        for page_url in _loc_values(root, "url"):
            try:
                normalized = validate_url_reference(page_url, scope=scope)
            except URLSafetyError:
                if len(rejected_urls) < MAX_SITEMAP_URLS:
                    rejected_urls.append(page_url)
                continue
            if normalized in discovered_set:
                continue
            if len(discovered_urls) >= MAX_SITEMAP_URLS:
                url_limit_reached = True
                break
            discovered_set.add(normalized)
            discovered_urls.append(normalized)

    return SitemapInspection(
        status=_aggregate_sitemap_status(documents),
        documents=documents,
        discovered_urls=discovered_urls,
        rejected_urls=rejected_urls,
        document_limit_reached=document_limit_reached or bool(queue),
        url_limit_reached=url_limit_reached,
    )


async def _inspect_llms_txt(
    source_url: str,
    client: httpx.AsyncClient,
    validator: URLSafetyValidator,
    scope: str,
) -> LlmsTxtInspection:
    try:
        fetched = await fetch_with_safe_redirects(
            client, source_url, validator, scope, max_bytes=MAX_LLMS_TXT_BYTES
        )
    except (SecureFetchFailure, URLSafetyError) as exc:
        return LlmsTxtInspection(
            source_url=source_url, status=SurfaceStatus.UNAVAILABLE, error=str(exc)
        )
    status = _surface_status(fetched.status_code)
    if status is not SurfaceStatus.PRESENT:
        return LlmsTxtInspection(
            source_url=source_url,
            final_url=fetched.final_url,
            status=status,
            error=(
                None
                if status is SurfaceStatus.MISSING
                else f"HTTP request returned status {fetched.status_code}"
            ),
        )

    raw_text = fetched.body.decode("utf-8", errors="replace")
    title_match = re.search(r"(?m)^[ \t]*#[ \t]+(.+?)[ \t]*$", raw_text)
    quote_lines = [
        line.lstrip()[1:].strip()
        for line in raw_text.splitlines()
        if line.lstrip().startswith(">")
    ]
    links: list[LlmsLink] = []
    rejected_links: list[str] = []
    seen: set[str] = set()
    matches = _MARKDOWN_LINK.findall(raw_text)
    for raw_link in matches[:MAX_LLMS_LINKS]:
        try:
            normalized = validate_url_reference(urljoin(fetched.final_url, raw_link))
        except URLSafetyError:
            rejected_links.append(raw_link)
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        hostname = urlsplit(normalized).hostname
        links.append(
            LlmsLink(
                url=normalized,
                internal=bool(hostname and is_within_scope(hostname, scope)),
            )
        )

    return LlmsTxtInspection(
        source_url=source_url,
        final_url=fetched.final_url,
        status=SurfaceStatus.PRESENT,
        raw_text=raw_text,
        title=title_match.group(1).strip() if title_match else None,
        summary=" ".join(quote_lines) or None,
        links=links,
        rejected_links=rejected_links,
        link_limit_reached=len(matches) > MAX_LLMS_LINKS,
    )


def _json_ld_types(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def inspect_structured_data(crawl_result: CrawlResult) -> StructuredDataInspection:
    items: list[StructuredDataItem] = []
    malformed_items: list[MalformedStructuredData] = []
    pages: set[str] = set()
    item_limit_reached = False
    nodes_visited = 0
    node_limit_reached = False
    traversal_stopped = False

    for page in crawl_result.pages:
        if traversal_stopped:
            break
        if page.status is not CrawlStatus.SUCCESS or not page.json_ld:
            continue
        source_url = page.final_url or page.requested_url
        pages.add(source_url)
        for block in page.json_ld:
            if traversal_stopped:
                break
            if isinstance(block, str):
                if len(malformed_items) < MAX_STRUCTURED_DATA_ITEMS:
                    malformed_items.append(
                        MalformedStructuredData(
                            source_page_url=source_url, raw_text=block
                        )
                    )
                else:
                    item_limit_reached = True
                continue
            stack: list[tuple[object, int]] = [(block, 0)]
            while stack:
                value, depth = stack.pop()
                if not isinstance(value, (dict, list)):
                    continue
                if nodes_visited >= MAX_STRUCTURED_DATA_NODES:
                    node_limit_reached = True
                    traversal_stopped = True
                    break
                nodes_visited += 1
                if depth > MAX_STRUCTURED_DATA_DEPTH:
                    continue
                if isinstance(value, dict):
                    types = _json_ld_types(value.get("@type"))
                    if types:
                        if len(items) >= MAX_STRUCTURED_DATA_ITEMS:
                            item_limit_reached = True
                            stack.clear()
                            break
                        items.append(
                            StructuredDataItem(
                                source_page_url=source_url,
                                types=types,
                                data=value,
                            )
                        )
                    children = list(value.values())
                    stack.extend(
                        (child, depth + 1) for child in reversed(children)
                    )
                else:
                    stack.extend(
                        (child, depth + 1) for child in reversed(value)
                    )

    encountered_types = sorted({item_type for item in items for item_type in item.types})
    if items:
        status = SurfaceStatus.PRESENT
    elif malformed_items:
        status = SurfaceStatus.MALFORMED
    else:
        status = SurfaceStatus.MISSING
    return StructuredDataInspection(
        status=status,
        pages_with_structured_data=len(pages),
        encountered_types=encountered_types,
        items=items,
        malformed_items=malformed_items,
        item_limit_reached=item_limit_reached,
        nodes_visited=nodes_visited,
        node_limit_reached=node_limit_reached,
    )


class CrawlTargetMismatchError(ValueError):
    """Raised when crawl evidence does not belong to the audited website scope."""


def _validate_crawl_result_scope(crawl_result: CrawlResult, scope: str) -> None:
    urls = [crawl_result.target_url]
    for page in crawl_result.pages:
        urls.append(page.requested_url)
        if page.final_url:
            urls.append(page.final_url)
    for url in urls:
        try:
            validate_url_reference(url, scope=scope)
        except URLSafetyError as exc:
            raise CrawlTargetMismatchError(
                f"crawl result URL is outside the audited target scope: {url}"
            ) from exc


async def inspect_machine_readable_surfaces(
    target_url: str,
    crawl_result: CrawlResult,
    *,
    client: httpx.AsyncClient | None = None,
    validator: URLSafetyValidator | None = None,
) -> MachineReadableAudit:
    safety = validator or URLSafetyValidator()
    normalized_target = await safety.validate(target_url)
    origin = _origin_url(normalized_target)
    hostname = urlsplit(origin).hostname
    assert hostname is not None
    scope = company_scope(hostname)
    _validate_crawl_result_scope(crawl_result, scope)
    robots_url = urljoin(origin, "robots.txt")
    sitemap_url = urljoin(origin, "sitemap.xml")
    llms_url = urljoin(origin, "llms.txt")

    owns_client = client is None
    http_client = client or create_crawler_client()
    try:
        robots = await _inspect_robots(robots_url, http_client, safety, scope)
        sitemap = await _inspect_sitemaps(
            sitemap_url,
            robots.sitemap_urls,
            http_client,
            safety,
            scope,
        )
        llms_txt = await _inspect_llms_txt(llms_url, http_client, safety, scope)
    finally:
        if owns_client:
            await http_client.aclose()

    structured_data = inspect_structured_data(crawl_result)
    summary = MachineReadableSummary(
        robots_status=robots.status,
        sitemap_status=sitemap.status,
        sitemap_urls_discovered=len(sitemap.discovered_urls),
        llms_txt_status=llms_txt.status,
        llms_txt_links_discovered=len(llms_txt.links),
        structured_data_status=structured_data.status,
        structured_data_pages=structured_data.pages_with_structured_data,
        structured_data_types=structured_data.encountered_types,
    )
    return MachineReadableAudit(
        target_url=normalized_target,
        robots=robots,
        sitemap=sitemap,
        llms_txt=llms_txt,
        structured_data=structured_data,
        summary=summary,
    )
