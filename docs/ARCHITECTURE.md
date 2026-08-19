# Architecture

AnswerLens uses a Next.js frontend and a FastAPI backend. The backend currently provides a health endpoint, secure bounded website crawling, deterministic machine-readable surface inspection, strict brand/evidence domain contracts, a typed Gemini structured-output provider, bounded Brand Intelligence and Claim Evidence Map agents, and a bounded external GEO intelligence layer for recommendation-query generation, Tavily evidence retrieval, competitor evidence discovery, and grounded query-readiness evaluation.

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

## Core brand and evidence domain contracts

`backend/schemas/brand.py` and `backend/schemas/evidence.py` define application-owned Pydantic contracts for later structured processing. This layer performs data validation only: it does not call an LLM, fetch evidence, resolve DNS, or decide support automatically.

`BrandProfile` holds a required brand name plus optional category and positioning fields, bounded audience, capability, and use-case lists, and bounded candidate `BrandClaim` records. A candidate claim is only a proposition; its existence does not imply factual verification.

`EvidenceReference` preserves a normalized HTTP/HTTPS URL, a required excerpt, and one explicit source type: owned webpage, structured data, `llms.txt`, brand-owned external, or independent external. URL validation reuses the non-resolving reference-safety boundary and rejects malformed, non-HTTP, credential-bearing, localhost, and literal non-global/private-IP URLs without DNS resolution or network access. Structured-data and `llms.txt` sources remain publisher-provided evidence types, not independent verification.

`ClaimEvidence` connects one candidate claim to an explicit support state (`supported`, `insufficient_evidence`, or `assumption`), evidence references, a `low`/`medium`/`high` confidence level, and a required human-readable confidence reason. Unsupported and assumption states may contain no evidence. A supported state requires at least one explicit evidence reference; validation never manufactures one.

Every Task 3 model rejects unknown fields, trims surrounding string whitespace, rejects empty important strings, and uses default factories for lists. Output is bounded as follows:

- Audiences per profile: 10
- Capabilities per profile: 20
- Use cases per profile: 15
- Candidate claims per profile: 30
- Evidence references per claim: 10
- Brand name and category: 200 characters each
- Audience entries: 200 characters
- Capability and use-case entries: 300 characters
- Positioning and evidence excerpts: 2,000 characters
- Claim statements and confidence reasons: 1,000 characters
- Evidence URLs: 2,048 characters

## Gemini structured-output provider

`backend/providers/base.py` defines the application-facing asynchronous `StructuredOutputProvider` contract. Callers provide a prompt and an application-owned Pydantic response model and receive that validated model rather than an untyped dictionary.

`backend/providers/gemini.py` implements this contract using the official Google Gen AI SDK and the project-selected `gemini-2.5-flash` model. Real provider construction reads `GEMINI_API_KEY` from the environment. Tests and other controlled callers can inject a client so automated verification requires neither credentials nor network access.

The provider requests `application/json` structured output and supplies the caller-provided Pydantic model as Gemini's response schema. Returned response text is still validated again with the same application-owned Pydantic model using `model_validate_json()`. Empty, malformed, schema-invalid, or unexpected-extra-field output therefore cannot silently become valid application data.

Invalid structured output is retried within an explicit bound of two total generation attempts: the initial generation plus at most one retry. This provider-level retry handles malformed or invalid model output only and is separate from the later autonomous evidence-research retry loop.

Configuration failures and Gemini request/API failures remain explicit and are not converted into fabricated output. Error messages do not expose the configured API key, while underlying exceptions are preserved as causes where useful.

The Gemini provider layer does not contain Brand Intelligence prompts, crawler-evidence interpretation, claim verification, Tavily retrieval, LangGraph orchestration, GEO scoring, persistence, or frontend behavior. Those responsibilities remain in later application layers.

### Gemini provider dependencies

- `google-genai==2.18.1`
- `pydantic==2.12.5`
- Model: `gemini-2.5-flash`
- Maximum structured-output attempts: 2

## Brand Intelligence Agent

`backend/agents/brand_agent.py` implements the Brand Intelligence extraction stage. It consumes an existing `CrawlResult`, an existing `MachineReadableAudit`, an injected `StructuredOutputProvider`, and an optional user-supplied business category. It does not crawl, refetch pages, resolve DNS, perform external search, or depend directly on Gemini.

The agent first prepares a deterministic bounded evidence representation from successful crawl pages. Failed crawl records are excluded from usable evidence. Each retained page receives a stable `page_N` source label and preserves its requested URL, final URL where available, title, meta description, headings, and readable page content within explicit prompt-size bounds.

Machine-readable observations are added separately and remain explicitly publisher-provided, untrusted evidence. Present `llms.txt` title and summary information may be included within bounds, along with encountered structured-data types and their source pages. Malformed structured data is not promoted to valid structured evidence. Neither `llms.txt` nor JSON-LD is treated as independent verification.

The Brand Intelligence prompt establishes its extraction rules before inserting source material. Crawled content, metadata, headings, `llms.txt`, structured-data observations, and user-supplied category context are treated as untrusted data rather than instructions. The prompt explicitly instructs the model to ignore prompt-injection attempts in source material, avoid outside knowledge, avoid unsupported factual invention, and leave optional information empty when the supplied evidence is insufficient.

Optional business-category input is normalized, bounded, serialized as data, and placed inside a separately delimited `USER-SUPPLIED CONTEXT (UNTRUSTED DATA)` section. It may help interpret ambiguous evidence but is not represented as independent website evidence. The model is explicitly instructed to treat this context only as data and not allow it to override the extraction rules.

The extraction function requests the existing application-owned `BrandProfile` model through `StructuredOutputProvider`. It does not import or configure Gemini directly and does not duplicate provider-level structured-output retry behavior. If no successful crawl evidence exists, extraction fails explicitly before the provider is called. Provider failures remain visible and no fallback or fabricated `BrandProfile` is produced.

Candidate `BrandClaim` values generated at this stage remain unverified propositions. The Brand Intelligence Agent does not create `ClaimEvidence`, assign support states, assign confidence, or claim that generated propositions are verified. Those responsibilities remain deferred to the Claim Evidence Map stage.

### Brand Intelligence evidence limits

- Maximum successful website pages included: 8
- Maximum readable content per page: 4,000 characters
- Maximum headings per page: 12
- Maximum characters per heading: 200
- Maximum meta-description length: 500 characters
- Maximum `llms.txt` title length: 300 characters
- Maximum `llms.txt` summary length: 1,000 characters
- Maximum structured-data types included: 40
- Maximum total prepared evidence length: 40,000 characters
- Optional category length follows the existing domain-schema category bound

Evidence truncation is deterministic. The agent performs no preliminary LLM summarization and no random evidence sampling.

## Claim Evidence Map Agent

`backend/agents/evidence_agent.py` implements the local Claim Evidence Map stage. It consumes an existing `BrandProfile`, `CrawlResult`, `MachineReadableAudit`, and injected `StructuredOutputProvider`, and returns the application-owned `ClaimEvidenceMap` contract.

The agent performs no crawling, DNS resolution, Tavily retrieval, external search, or direct Gemini configuration. It works only from evidence already collected by earlier stages.

The local evidence catalog includes successful crawled webpages, present `llms.txt` observations, and retained publisher structured-data observations. Failed crawl pages are excluded. Robots and sitemap status are not treated as claim evidence.

Each evidence source preserves its URL, explicit source type, and bounded source text. Source text is JSON-encoded before insertion into the model prompt and explicitly labeled as untrusted data so instruction-like strings or prompt delimiters appearing inside publisher content remain data rather than prompt structure.

The model must return exactly one `ClaimEvidence` record for every candidate `BrandClaim`, preserving the original claim wording and order. Application-side validation independently enforces this invariant and rejects omitted, added, duplicated, rewritten, or reordered claims.

Evidence references are validated against the prepared local catalog. The evidence URL and source type must match a supplied source, external source types are rejected at this stage, and each normalized evidence excerpt must occur in the corresponding prepared source text. An `assumption` record must contain no evidence.

A `supported` classification means only that the supplied publisher evidence directly and materially supports the proposition. It does not mean AnswerLens independently verified the claim. `insufficient_evidence` represents partial, ambiguous, or incomplete grounding. Confidence describes confidence in the support classification from the supplied evidence; it is not a truth probability, GEO score, ranking probability, mention probability, or citation probability.

Schema-valid outputs that violate application grounding invariants may be retried once, for a maximum of two semantic attempts. Provider/API failures propagate directly rather than entering this semantic-repair loop. If the brand profile contains no claims, the agent returns an empty map without calling the provider. If claims exist but no usable local evidence exists, the stage fails explicitly before provider execution.

### Claim Evidence Map limits

- Maximum successful website pages considered: 8
- Maximum readable content per page: 4,000 characters
- Maximum headings per page: 12
- Maximum heading length: 200 characters
- Maximum meta-description length: 500 characters
- Maximum `llms.txt` title length: 300 characters
- Maximum `llms.txt` summary length: 1,000 characters
- Maximum structured-data observations considered: 40
- Maximum structured-data text per observation: 4,000 characters
- Maximum total rendered evidence-source representation: 40,000 characters
- Maximum semantic attempts: 2
- Claim Evidence Map records remain bounded by the existing maximum of 30 candidate brand claims

The 40,000-character evidence bound is applied to the actual rendered JSON-encoded source representation, not only to raw source text. Deterministic prefix fitting ensures that JSON escaping cannot cause the final evidence prompt section to exceed the configured bound.

## External GEO Intelligence Layer

Task 7 adds the bounded external GEO intelligence stage. It connects recommendation-query generation, Tavily web research, external-source classification, competitor evidence, and Gemini-grounded query evaluation without yet introducing LangGraph orchestration or the autonomous evidence-research loop.

The application-level flow is:

```text
BrandProfile
    +
ClaimEvidenceMap
        ↓
generate recommendation queries
        ↓
retrieve bounded Tavily evidence
        ↓
validate and classify external sources
        ↓
run grounded query evaluations
        ↓
ExternalGeoEvaluation

```

`backend/services/external_geo.py` exposes this vertical slice as an application-service helper. It does not persist audits, expose a public audit endpoint, or perform autonomous follow-up research.

### Query Intelligence

`backend/agents/query_agent.py` generates a bounded `RecommendationQuerySet` using the application-facing `StructuredOutputProvider`.

Queries are derived from the supplied `BrandProfile` rather than from a fixed template list. The supported intent families are:

- `category_discovery`
- `alternative_comparison`
- `audience_use_case`
- `problem_driven`
- `capability_driven`

The model is asked to prefer approximately 8–12 useful buyer-style queries when the supplied evidence supports that variety. Sparse profiles may legitimately produce fewer queries rather than forcing invented categories, audiences, capabilities, use cases, or competitors.

`RecommendationQuerySet` permits at most 12 queries. Query text and rationale are bounded, unexpected fields are rejected, and normalized duplicate queries are rejected deterministically.

Optional known competitors are normalized, deduplicated, bounded to 10 values, and treated only as unverified user-supplied hints. They do not become evidence-backed competitors unless retrieved external evidence supports them.

Brand-profile and competitor context is serialized into explicit untrusted-data sections. The prompt prohibits browsing, outside knowledge, unsupported capability invention, and treating embedded instruction-like content as prompt instructions.

The rendered profile context is bounded to 20,000 characters after JSON encoding rather than only before serialization.

### Search Provider Boundary

`backend/providers/search.py` defines the application-facing asynchronous `SearchProvider` protocol and transport-level `RawSearchResult` representation.

`backend/providers/tavily.py` implements this boundary using the official asynchronous Tavily client. Real provider construction reads `TAVILY_API_KEY` from the environment. Injected clients allow tests to run without credentials or live network requests.

The Tavily search configuration is intentionally constrained:

- Search topic: `general`
- Search depth: `basic`
- Maximum results requested per query: 5
- Tavily-generated answers: disabled
- Raw page content: disabled
- Automatic search-parameter expansion: disabled

AnswerLens uses Tavily as a bounded external retrieval source. Tavily is not used to generate the final GEO judgment, and returned result URLs are not independently crawled or fetched during this stage.

### External Research Validation

`backend/services/search.py` performs bounded research for generated queries.

At most three Tavily searches execute concurrently, while the returned research batch preserves the original recommendation-query order.

Each retained Tavily result preserves:

- normalized URL
- normalized host/domain
- bounded title
- bounded Tavily content
- deterministic source ownership
- optional Tavily relevance metadata

Result URLs reuse the non-resolving URL-reference safety boundary. Only HTTP/HTTPS references are retained. Malformed URLs, credential-bearing URLs, localhost names, literal non-global/private IP references, and other invalid references are discarded without DNS resolution or fetching.

Results are deduplicated deterministically by normalized URL and limited to five usable sources per query.

Source ownership is classified deterministically from the audited target scope:

- `brand_owned` for the audited website/same-site scope
- `independent` for other valid external domains

A third-party source is not classified as brand-owned merely because its content mentions the brand.

A successful Tavily search containing zero usable results is distinct from a provider/request failure. Search-provider failures become explicit failed research records. Unexpected internal programming exceptions are not silently converted into search failures.

Malformed Tavily response structures are treated as provider failures rather than as successful searches with zero evidence.

### Grounded Query Evaluation

`backend/agents/evaluation_agent.py` evaluates one recommendation query at a time through the existing `StructuredOutputProvider`.

Evaluation input may contain:

- the exact `RecommendationQuery`
- bounded `BrandProfile` context
- the existing local `ClaimEvidenceMap`
- validated Tavily results for that query
- optional known-competitor hints

Local Task 6 claim evidence remains publisher-context evidence and is not relabeled as independent external evidence.

The Task 7 `QueryEvaluation` contract represents:

- exact query text
- evaluation status
- readiness
- supporting external evidence
- missing evidence
- competitor evidence
- confidence
- human-readable reason

Readiness is qualitative:

- `low`
- `medium`
- `high`

It represents evidence readiness for the supplied recommendation intent. It is not a product-quality score, market rank, answer-engine ranking probability, mention probability, or citation probability.

Confidence remains `low`, `medium`, or `high` and represents confidence in the supplied-evidence classification, not the probability that an answer engine will mention the brand.

A completed `medium` or `high` readiness evaluation must contain at least one supporting external evidence reference. `low` readiness may legitimately contain no supporting evidence after a successful external search.

If external retrieval fails, the evaluation is explicitly `unavailable`; retrieval infrastructure failure is not converted into a fake low-readiness judgment.

### Application-Side External Evidence Grounding

Gemini output is not trusted merely because it satisfies the Pydantic schema.

For each supporting external evidence reference, application-side validation requires:

1. the URL to exist in the validated Tavily catalog for that exact query
2. the returned source ownership to match the deterministic catalog classification
3. the whitespace-normalized excerpt to occur in the bounded source title/content representation

Unknown or fabricated URLs and fabricated/paraphrased excerpts that cannot be grounded in the supplied source are rejected.

Competitor evidence follows the same URL, ownership, and excerpt grounding checks. In addition, the competitor name must occur in at least one of its cited external sources. User-supplied known competitors therefore cannot silently become externally verified competitors.

Every completed evaluation must preserve the exact original recommendation-query text.

Schema-valid output that violates these semantic grounding invariants may receive one repair attempt, for a maximum of two semantic attempts total. Provider/API exceptions propagate immediately and do not enter the semantic-repair loop.

This semantic retry is only output repair. It is not the later autonomous evidence-gathering loop.

### External Evaluation Trust Boundary

Brand-profile values, local claim evidence, known-competitor hints, Tavily result titles, and Tavily result content are treated as untrusted data.

External sources are serialized as JSON before prompt insertion. The prompt explicitly prohibits following instructions contained inside retrieved content, browsing outside the supplied data, inventing URLs, inventing excerpts, and using remembered competitor knowledge.

Prepared external source rendering is bounded to 30,000 characters and application context to 20,000 characters. Limits are applied against the actual rendered JSON representation so escape-heavy content cannot silently exceed the configured prompt budget.

### Task 7 Limits

- Maximum recommendation queries: 12
- Maximum Tavily results per query: 5
- Maximum concurrent searches: 3
- Maximum known competitors supplied to query generation: 10
- Maximum query length: 500 characters
- Maximum query rationale: 1,000 characters
- Maximum Tavily title retained: 500 characters
- Maximum Tavily content retained per result: 4,000 characters
- Maximum external evidence references per evaluation: 10
- Maximum missing-evidence entries per evaluation: 10
- Maximum competitor-evidence entries per evaluation: 10
- Maximum competitor-name length: 200 characters
- Maximum evaluation reason: 2,000 characters
- Maximum rendered external-source context: 30,000 characters
- Maximum rendered application context: 20,000 characters
- Maximum semantic evaluation attempts: 2

Task 7 intentionally does not implement LangGraph, confidence-based research routing, follow-up Tavily searches, Evidence Gap diagnosis, GEO experiments, metrics, execution tracing, database persistence, audit APIs, or frontend audit screens. Those remain later workflow/product layers.