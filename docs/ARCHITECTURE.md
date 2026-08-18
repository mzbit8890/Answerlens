# Architecture

AnswerLens uses a Next.js frontend and a FastAPI backend. The backend currently exposes its Task 0 health check and provides a deterministic website evidence crawler as an internal service.

## Website crawler

`backend/services/crawler.py` owns bounded crawl orchestration. It starts from one validated public HTTP or HTTPS URL, fetches HTML without executing JavaScript, discovers same-site links, and selects pages using deterministic path-based priorities. Exact authentication and legal path segments, plus asset, media, and downloadable-file extensions, are excluded from the crawl queue. Segment matching avoids excluding legitimate content paths such as `/accounting-software` and `/long-term-planning`.

The crawler returns Pydantic models from `backend/schemas/crawl.py`. Each page preserves its requested source URL and, on success, its final URL after redirects. An individual fetch, content-type, timeout, redirect, or size failure becomes an explicit failed page record; previously collected pages remain available.

## URL and network safety boundary

`backend/guardrails/url_safety.py` normalizes and validates every initial URL and redirect destination. Only HTTP and HTTPS are accepted. Credentials, localhost names, loopback, private, link-local, reserved, multicast, unspecified, and other non-global IP addresses are rejected.

Preflight URL validation resolves hostnames and requires every returned address to be globally routable. The crawler-owned HTTPX client also uses `PublicIPNetworkBackend` at the HTTPCore socket boundary. At connection time, this backend resolves the original hostname, rejects the complete answer set if any address is non-public, and passes a validated numeric address directly to the underlying TCP connector. The HTTP request URL and Host header remain unchanged, and HTTPCore supplies the original hostname for TLS SNI and certificate verification. HTTPS verification is not disabled.

This connection-time pinning closes the DNS time-of-check/time-of-use gap for crawler-owned clients: the TCP connector does not independently resolve the hostname after validation. The crawler-owned client also sets `trust_env=False`, so environment proxy and certificate configuration cannot redirect crawler traffic. HTTPX 0.28.1 and HTTPCore 1.0.9 are pinned because HTTPX does not expose custom network backends directly and the transport configures the pinned HTTPCore connection-pool boundary.

Redirects are followed manually so their destination is scope-checked and preflight-validated before the next request; the connection backend then independently enforces public-IP pinning at socket creation. Fetches remain within the normalized target host scope, including its `www` form and subdomains; arbitrary cross-domain redirects and links are rejected.

Externally injected HTTPX clients are retained only as a caller-controlled test seam. They still receive URL and redirect validation, but their connection behavior is not controlled by AnswerLens and therefore is not covered by the connection-pinning guarantee. Production crawling uses the crawler-owned client.

## HTML extraction boundary

`backend/services/html_extractor.py` parses untrusted HTML with Beautiful Soup's non-executing HTML parser. It extracts the page title, meta description, headings, readable text, links, and JSON-LD blocks. Script, style, navigation, header, footer, form, and similar boilerplate elements are removed from readable content. The extractor does not summarize, interpret, execute, or follow instructions in page content. Invalid JSON-LD is preserved as untrusted text rather than treated as validated structured data.

## Crawl limits

- Maximum returned pages: 8
- Per-request timeout: 10 seconds
- Maximum response body: 2,000,000 bytes, enforced from both `Content-Length` and streamed bytes
- Maximum redirects per page: 5

URLs are normalized before queueing and tracked in queued and visited sets, preventing duplicate pages from consuming crawl capacity.

## Machine-readable surface inspection

`backend/services/machine_readable.py` inspects `robots.txt`, `sitemap.xml`, robots-declared sitemaps, `llms.txt`, and JSON-LD already present in a supplied crawl result. It returns the Pydantic models in `backend/schemas/machine_readable.py`, including distinct `present`, `missing`, `unavailable`, and `malformed` states. A failure in one surface does not remove results from the others.

Before combining these sources, the inspector verifies that the crawl result target and every requested/final crawl page URL belong to the audited target scope. The same `www` and subdomain rules used by the crawler are accepted. A different-site crawl result raises an explicit error before its JSON-LD can be mixed into the audit.

### Secure fetch reuse

Task 1's manual redirect validation and streamed response limiting are shared through `backend/services/secure_fetch.py`. Both the crawler and machine-readable inspector use this boundary. Production inspection creates the same crawler-owned HTTPX client, including connection-time public-IP pinning, normal TLS verification, the `AnswerLensCrawler/1.0` identity, the 10-second timeout, and `trust_env=False`. Injected clients remain a test seam.

URLs that will actually be fetched, including sitemap documents, continue through full DNS/public-IP validation and connection-time pinning. References retained only as data use a separate non-resolving validator: it normalizes HTTP/HTTPS URLs, rejects credentials, localhost names, malformed URLs, literal non-global IPs, and out-of-scope sitemap page references without performing DNS lookups. If a retained reference is fetched by a future task, it must first cross the full network boundary.

### robots.txt

The inspector retains bounded raw text, source and final URLs, parse state, sitemap directives, and deterministic `User-agent`, `Allow`, and `Disallow` rules. Unusual non-directive lines are counted and produce a malformed parse state without discarding recognized data. Because this inspector receives an already completed crawl result, Task 2 records robots policy but does not retroactively claim that it governed those prior crawl requests.

### Sitemaps

The inspector checks `/sitemap.xml` and safe same-scope sitemap locations declared by robots. It supports `urlset` and basic `sitemapindex` documents. Sitemap documents receive full network validation because they are fetched. Page URLs in `urlset` are only retained: they receive non-resolving syntactic, literal-address, and scope validation, then normalization and deduplication. Private literal, malformed, credential-bearing, localhost, and out-of-scope locations are rejected visibly.

Sitemap XML is parsed with pinned `defusedxml`, which rejects entity expansion and external-entity constructs. The inspector does not fetch pages listed in a sitemap.

### llms.txt

The optional `/llms.txt` inspection retains bounded untrusted text and deterministically extracts a Markdown H1, block-quote summary text, and deduplicated Markdown links. Links are classified as internal or external using non-resolving reference validation and are not fetched. Presence is recorded only as an observable publisher-provided surface, not a ranking or citation signal.

### Structured data

JSON-LD is reused from successful crawl pages without refetching them. Bounded iterative traversal supports dictionaries, lists, nested values, `@graph`, string `@type`, and array `@type`. Known and unknown types are retained with their source page URL. Invalid JSON-LD text stays in a separate malformed collection and never becomes a structured-data item. A global dictionary/list-node budget applies across the supplied crawl result; the result exposes both the number of visited nodes and whether traversal was truncated.

### Machine-readable limits

- Maximum robots body: 256,000 bytes
- Maximum retained robots sitemap directives: 10
- Maximum sitemap body per document: 2,000,000 bytes
- Maximum sitemap documents: 5
- Maximum retained sitemap page URLs: 500
- Maximum `llms.txt` body: 512,000 bytes
- Maximum retained `llms.txt` links: 100
- Maximum structured-data items: 500
- Maximum structured-data traversal depth: 20
- Maximum structured-data dictionary/list nodes visited: 5,000
