# Coding Agent Runs

# Task 0 — Repository Bootstrap

## Goal

Create the initial production-style AnswerLens development foundation with a minimal Next.js frontend, a minimal FastAPI backend, starter repository documentation, and no AnswerLens product features.

## Completion Criteria

- The Next.js frontend installs and passes a production build or appropriate type check.
- The FastAPI backend starts successfully.
- `GET /health` returns a successful health response.
- The health endpoint has a passing Pytest test.
- The intended frontend, backend, and documentation structure exists.
- No product features or secrets are introduced.
- Relevant verification commands are actually executed.

## Changes

- Created a Next.js 16 frontend using React, TypeScript, and Tailwind CSS.
- Added a minimal AnswerLens placeholder page and retained starter-level styling.
- Created a FastAPI backend with only `GET /health`, returning `{"status": "healthy"}`.
- Added one Pytest test for the health endpoint.
- Added empty tracked directories for future `api`, `agents`, `graph`, `providers`, `services`, `models`, `schemas`, and `guardrails` modules.
- Added `README.md`, `.gitignore`, `.env.example`, pinned Python requirement files, and the npm lockfile.
- Added the requested starter documentation files while preserving `docs/PROJECT_SPEC.md` unchanged.
- Added only blank future variable names to `.env.example`: `GEMINI_API_KEY`, `TAVILY_API_KEY`, and `DATABASE_URL`.

## Verification

- `npm.cmd install` — completed successfully after the retry and generated `package-lock.json`. The final install audited 359 packages and reported 0 vulnerabilities.
- `npm.cmd run lint` — passed with no warnings or errors after the PostCSS configuration repair.
- `npm.cmd run build` — passed. Next.js compiled successfully, TypeScript finished successfully, and all three static pages were generated.
- `.\\.venv\\Scripts\\python.exe -m pip install -r requirements-dev.txt` — installed all pinned backend and test dependencies successfully inside `backend/.venv`.
- `.\\.venv\\Scripts\\python.exe -m pytest` — passed with `1 passed in 0.86s`.
- A Uvicorn process was started with `.\\.venv\\Scripts\\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8765`, followed by `Invoke-RestMethod -Uri 'http://127.0.0.1:8765/health' -TimeoutSec 2` — returned `{"status":"healthy"}`. The verification process was then stopped.
- `git status --short --ignored` filtered for generated environments — confirmed `backend/.venv/`, `frontend/.next/`, and `frontend/node_modules/` were ignored.

## Iterations / Failures

- The first toolchain check found Node.js `v26.7.0`, but PowerShell blocked `npm.ps1`; subsequent npm commands used `npm.cmd`.
- No usable Python interpreter or Python environment manager was initially available. The official Python 3.13.7 per-user runtime was installed, after which `backend/.venv` was created.
- The initial sandboxed `npm.cmd install` timed out after 120 seconds. It was retried with approved network access. That retry crossed its 180-second command timeout, but npm reported that it had added 356 packages and completed its audit.
- The initial dependency set used Next.js 16.1.6. `npm.cmd audit --omit=dev` reported three high-severity vulnerabilities. Next.js and related frontend packages were updated to patched versions; the subsequent `npm.cmd install` completed successfully and reported 0 vulnerabilities.
- The first lint/build run produced one lint warning for an anonymous default export in `postcss.config.mjs`; the configuration was changed to export a named constant. The final lint run was clean.
- One combined lint/tool-discovery command exited nonzero because `winget` was not installed; the lint portion itself completed successfully.

## Final Result

All Task 0 acceptance criteria were satisfied. The frontend installed, linted, and built successfully; the backend test passed; a live Uvicorn health request succeeded; the required initial structure exists; no secrets were added; and no AnswerLens product features were implemented.


## Human Review

- [ ] Frontend manually opened and verified at localhost:3000.
- [ ] Repository status reviewed.
- [ ] Git working tree confirmed clean after commit.

# Task 1 — Secure Website Evidence Crawler

## Goal

Implement a deterministic, security-conscious crawler that collects structured evidence from a small set of useful pages on one public company website without implementing AI reasoning or later AnswerLens features.

## Completion Criteria

- Accept safe public HTTP and HTTPS targets while rejecting local, private, link-local, and otherwise unsafe destinations.
- Resolve hostnames before connecting and revalidate every redirect destination.
- Remain within the target website scope, normalize and deduplicate URLs, and return no more than eight selected pages.
- Apply bounded timeouts, redirect limits, HTML-only extraction, and a maximum response-size limit.
- Extract requested and final source URLs, title, meta description, headings, readable text, internal links, and JSON-LD.
- Represent individual failures explicitly without discarding successful pages.
- Preserve the Task 0 health behavior and pass the complete backend test suite without live-network test dependencies.

## Changes

- Added Pydantic crawl result and page schemas with explicit success and failure states.
- Added URL normalization, company-scope checks, async DNS resolution, and rejection of non-global IP destinations.
- Added manual safe-redirect handling, deterministic useful-page prioritization, low-value URL filtering, URL deduplication, and an eight-page cap.
- Added a 10-second request timeout, five-redirect cap, HTML media-type enforcement, HTTP failure handling, and a 2,000,000-byte streamed response limit.
- Added Beautiful Soup extraction for metadata, headings, readable content, links, and JSON-LD while removing common boilerplate and non-content elements.
- Added crawler, URL safety, and HTML extraction tests using injected DNS and `httpx.MockTransport`; automated tests do not access the internet.
- Moved `httpx` into runtime requirements and added pinned `beautifulsoup4==4.13.4`.

## Verification

- `.\\.venv\\Scripts\\python.exe -m pip install -r requirements-dev.txt` — passed and installed Beautiful Soup 4.13.4 plus its parser dependency.
- `.\\.venv\\Scripts\\python.exe -m pytest tests/test_url_safety.py tests/test_html_extractor.py tests/test_crawler.py -q` — initial focused result: 23 passed and 1 failed.
- `.\\.venv\\Scripts\\python.exe -m pytest tests/test_crawler.py::test_redirect_to_unsafe_destination_is_rejected -q` — passed after the redirect-classification repair.
- `.\\.venv\\Scripts\\python.exe -m pytest -q` — passed with 25 tests after that repair.
- `.\\.venv\\Scripts\\python.exe -m pytest tests/test_crawler.py::test_oversized_streamed_response_is_rejected_without_content_length -q` — passed after adding explicit streamed-body coverage.
- Final `.\\.venv\\Scripts\\python.exe -m pytest -q` — passed with 26 tests in 0.66 seconds, including the existing Task 0 health test.
- `.\\.venv\\Scripts\\python.exe -m pip check` — passed with `No broken requirements found.`
- `.\\.venv\\Scripts\\python.exe -m compileall -q main.py guardrails schemas services tests` — passed.
- A controlled live invocation of `crawl_website('https://example.com', max_pages=2)` — succeeded with one page: requested and final URL `https://example.com/`, status `success`, title `Example Domain`, no failure, and 127 extracted content characters.

## Iterations / Failures

- The first focused test run had one failure. A redirect to `127.0.0.1` was safely rejected, but it was classified as outside the target scope before being classified as a non-public address. URL validation was reordered for literal IP destinations so the explicit network-safety reason is reported; domain destinations remain scope-checked before DNS resolution. The affected test and full suite then passed.
- Additional streamed-body coverage was added after the initial green suite to verify that the response limit is enforced even when `Content-Length` is absent. That test passed on its first run, and the final full suite remained green.

## Final Result

All Task 1 acceptance criteria were satisfied. The crawler safely collected a real public HTML page, returned no more than the configured limit, rejected unsafe targets and redirects, preserved source attribution, extracted the required evidence fields, represented partial failures explicitly, and passed all 26 backend tests.

## Human Review

- [ ] Crawler implementation and security boundaries reviewed.
- [ ] Test coverage and live verification output reviewed.
- [x] Repository diff reviewed before commit.

### Human Review Hardening

These findings were identified during human review after the initial Task 1 implementation and its 26-test green run. They were not findings from the original Codex implementation cycle.

#### Issues found during human review

- Preflight DNS validation and HTTPX connection establishment used separate hostname resolutions, leaving a DNS rebinding time-of-check/time-of-use gap.
- The crawler-owned HTTPX client did not explicitly disable environment proxy and networking configuration.
- Low-value URL filtering used substring matches, causing legitimate paths such as `/accounting-software` to match the blocked `account` term.

#### Changes made

- Added a custom HTTPCore async network backend that resolves at connection time, rejects the entire DNS answer set if any address is non-public, and gives the underlying TCP connector a validated numeric address rather than the hostname.
- Added an HTTPX transport backed by that network boundary. The original request hostname remains in the HTTP Host header and is supplied to TLS for SNI and certificate verification; TLS verification remains enabled.
- Configured crawler-owned HTTPX clients with `trust_env=False`. Externally injected clients remain unchanged as a caller-controlled test seam.
- Replaced broad low-value substring matching with exact path-segment matching for authentication and legal paths.
- Declared and pinned the directly used HTTPCore 1.0.9 dependency alongside HTTPX 0.28.1.

#### Tests added

- Verified that the TCP backend receives only the validated numeric IP while the original HTTP Host header and TLS SNI hostname are preserved.
- Verified that a private connection-time DNS answer prevents any TCP connection attempt.
- Verified that a mixed public/private DNS answer set prevents any TCP connection attempt.
- Verified that crawler-owned clients set `trust_env=False`.
- Added regression coverage for all reviewed low-value paths and for `/accounting-software`, `/accounting/features`, `/long-term-planning`, and `/customer-accounting-platform`.

#### Failures and iterations

No test repair iteration was required during the human-review hardening implementation. The focused affected suite passed on its first run with 5 tests passing, followed by a green complete backend suite.

#### Final verification

- `.\\.venv\\Scripts\\python.exe -m pytest tests/test_network_safety.py tests/test_crawler.py::test_low_value_filter_uses_precise_path_segments tests/test_crawler.py::test_owned_client_disables_environment_network_configuration -q` — passed with 5 tests in 0.98 seconds.
- `.\\.venv\\Scripts\\python.exe -m pytest -q` — passed with 31 tests in 1.19 seconds.
- `.\\.venv\\Scripts\\python.exe -m pip check` — passed with `No broken requirements found.`
- `.\\.venv\\Scripts\\python.exe -m compileall -q main.py guardrails schemas services tests` — passed.
- A bounded live `crawl_website('https://example.com', max_pages=1)` regression — succeeded over HTTPS with status `success`, title `Example Domain`, and no TLS or crawl failure.

#### Remaining security limitation

The connection-pinning guarantee applies to AnswerLens-owned crawler clients. An externally injected HTTPX client controls its own transport and is not guaranteed to pin validated addresses; injection is retained for isolated tests and must not be used as the production network path. The custom transport also depends on the pinned HTTPX/HTTPCore connection-pool interface and must be reviewed when either dependency is upgraded. Network-layer attacks beyond DNS resolution and destination selection, such as compromise of globally routed infrastructure, are outside this crawler boundary.

# Task 2 — Machine-Readable Surface Inspector

## Goal

Implement a deterministic layer that safely inspects `robots.txt`, sitemaps, optional `llms.txt`, and JSON-LD already collected by the crawler, producing a structured evidence bundle without AI reasoning or GEO scoring.

## Completion Criteria

- Safely inspect `robots.txt`, `/sitemap.xml`, safe robots-declared sitemaps, and optional `/llms.txt` through the existing Task 1 network boundary.
- Distinguish present, missing, unavailable, and malformed states rather than treating all failures as missing.
- Bound response sizes, sitemap document traversal, retained sitemap URLs, `llms.txt` links, and structured-data traversal.
- Safely parse `urlset` and basic `sitemapindex` XML without external entities or entity expansion.
- Reuse crawled JSON-LD, detect nested and multiple schema types, preserve unknown types and source attribution, and keep malformed JSON-LD untrusted.
- Preserve all Task 0 and Task 1 behavior and pass the complete backend suite without live-network test dependencies.

## Implementation

- Extracted Task 1's manual safe-redirect and streamed-byte-limit behavior into a shared secure-fetch service; the existing crawler continues to use it with the same limits and failure behavior.
- Added Pydantic models for robots, sitemap documents and discoveries, `llms.txt`, structured-data items, malformed structured data, the combined audit, and its deterministic summary.
- Added bounded robots parsing for sitemap directives and `User-agent`, `Allow`, and `Disallow` rules. Policy is recorded but not retroactively applied to the supplied completed crawl.
- Added safe sitemap discovery from the default path, robots declarations, and bounded sitemap indexes. URLs are normalized, deduplicated, scope-checked, and safety-validated. Sitemap-listed pages are not fetched.
- Added pinned `defusedxml==0.7.1` for hostile XML parsing.
- Added bounded Markdown H1, block-quote, and link extraction for optional `llms.txt`; links are classified but not fetched.
- Added bounded iterative classification of nested JSON-LD, `@graph`, lists, and multiple `@type` values with source-page attribution.
- Added explicit constants for robots bytes/directives, sitemap bytes/documents/URLs, `llms.txt` bytes/links, and structured-data count/depth.

## Verification

- Initial `.\\.venv\\Scripts\\python.exe -m pytest tests/test_machine_readable.py tests/test_structured_data.py -q` — failed during collection with two import errors.
- Focused rerun after the import repair — 17 passed and 1 failed.
- Affected H1 test rerun — 1 passed in 0.26 seconds.
- Focused Task 2 rerun after the parser repair — 18 passed in 0.41 seconds.
- Expanded focused security/bounds run — 23 passed in 0.67 seconds.
- Final focused Task 2 run — 23 passed in 0.54 seconds.
- Final `.\\.venv\\Scripts\\python.exe -m pytest -q` — 54 passed in 1.57 seconds, including existing health, crawler, URL safety, and pinned-network tests.
- `.\\.venv\\Scripts\\python.exe -m pip check` — passed with `No broken requirements found.`
- `.\\.venv\\Scripts\\python.exe -m compileall -q main.py guardrails schemas services tests` — passed.
- Bounded live inspection of `https://example.com` after a one-page crawl — observed `robots.txt` missing, `sitemap.xml` missing, `llms.txt` missing, structured data missing, zero sitemap URLs, zero `llms.txt` links, and no structured-data types.

## Failures and repair iterations

- The initial focused test collection failed because `DefusedXmlException` was imported from `defusedxml.ElementTree`; version 0.7.1 defines it in `defusedxml.common`. The import was corrected and collection succeeded.
- The next focused run had one failure because the `llms.txt` H1 expression required `#` at column zero. The deterministic parser was updated to tolerate horizontal indentation around an H1, after which the affected and focused suites passed.
- The first live-verification command failed with a Python `SyntaxError` because an inline `async def` followed a semicolon. It made no network request. The command was rewritten using separate `asyncio.run` calls, and the bounded live inspection succeeded.
- After the first green full suite, sitemap candidate queue growth was explicitly capped in addition to fetch counts, and robots sitemap directive retention was bounded. The focused and complete suites remained green after this hardening.

## Final Result

All Task 2 acceptance criteria were satisfied. Each surface is independently inspectable through the existing secure network path; parsing and traversal are bounded; malformed and missing states remain explicit; structured-data attribution is preserved; and all 54 backend tests pass.

## Human Review

- [ ] Machine-readable implementation reviewed.
- [ ] Security and parsing boundaries reviewed.
- [ ] Test and live verification results reviewed.
- [ ] Repository diff reviewed before commit.

### Human Review Hardening

These findings were identified during human review after the initial Task 2 implementation completed with 54 passing backend tests. They were not identified during the original Codex Task 2 implementation cycle.

#### Findings

- Sitemap page references and `llms.txt` links were not fetched, but classification used the full URL validator and therefore performed unnecessary DNS lookups.
- Structured-data item and depth limits did not cap the total number of dictionary/list nodes visited in a wide JSON-LD structure.
- The separately supplied audit target and crawl result were not checked for same-site consistency before their evidence was combined.

#### Implementation changes

- Added non-resolving URL-reference validation that retains the existing HTTP/HTTPS, malformed URL, credential, localhost, literal non-global IP, normalization, and optional scope checks without resolving hostnames.
- Applied reference-only validation to sitemap page URLs and `llms.txt` links. Sitemap documents remain on full DNS/public-IP validation and the connection-time pinned fetch boundary because they are actually fetched.
- Added `MAX_STRUCTURED_DATA_NODES = 5_000`, global node counting across the crawl result, deterministic document-order traversal, and explicit `nodes_visited` and `node_limit_reached` result fields.
- Added a deterministic target/crawl invariant that checks the crawl target and every requested/final page URL against the audited site scope before any crawl evidence is combined.

#### Tests added

- Verified that retained sitemap page references on a subdomain do not invoke DNS resolution.
- Verified that retained internal and external `llms.txt` links do not invoke DNS resolution.
- Verified that malformed, credential-bearing, localhost, and literal-private `llms.txt` references remain rejected.
- Verified that robots-declared sitemap documents still invoke full DNS validation before fetch.
- Verified that wide JSON-LD traversal stops exactly at the node budget, reports truncation, and produces deterministic repeated results.
- Verified that existing nested `@graph` extraction remains below the node limit.
- Verified that matching and `www` crawl targets are accepted and a clearly different website crawl result is rejected explicitly.

#### Failures and iterations

No implementation repair iteration was required. The focused Task 2.1 suite passed on its first run, followed by a green complete backend suite.

#### Final verification

- `.\\.venv\\Scripts\\python.exe -m pytest tests/test_machine_readable.py tests/test_structured_data.py -q` — passed with 30 tests in 0.63 seconds.
- `.\\.venv\\Scripts\\python.exe -m pytest -q` — passed with 61 tests in 1.56 seconds.
- `.\\.venv\\Scripts\\python.exe -m pip check` — passed with `No broken requirements found.`
- `.\\.venv\\Scripts\\python.exe -m compileall -q main.py guardrails schemas services tests` — passed.

#### Remaining limitations

- Reference-only validation intentionally does not determine where a hostname would resolve because no connection occurs in Task 2. Any future fetch of a retained URL must pass full DNS validation and connection-time public-IP pinning first.
- Same-site consistency uses the existing crawler scope rule rather than registrable-domain ownership analysis. It is a deterministic integrity check, not proof of organizational ownership.

# Task 3 — Core Brand & Evidence Domain Schemas

## Goal

Define strict, reusable, application-owned Pydantic contracts for brand profiles, candidate claims, evidence references, claim support states, and confidence before any Gemini or Brand Intelligence implementation.

## Implementation

- Added `BrandProfile` with a required bounded brand name, optional category and positioning, bounded audience/capability/use-case lists, and bounded candidate claims.
- Added `BrandClaim` as a proposition-only record that does not encode verification.
- Added `EvidenceReference` with a locally validated HTTP/HTTPS URL, required excerpt, and explicit evidence source enum.
- Added practical source types for owned webpages, structured data, `llms.txt`, brand-owned external sources, and independent external sources.
- Added explicit `supported`, `insufficient_evidence`, and `assumption` support states plus `low`, `medium`, and `high` confidence levels.
- Added `ClaimEvidence` to connect a candidate claim to support status, bounded evidence references, confidence, and a required confidence reason.
- Required supported claims to include at least one explicit evidence reference while allowing insufficient-evidence and assumption states to remain empty.
- Configured all Task 3 models to reject unknown fields, trim and validate important strings, use safe list defaults, and enforce explicit demo-scale list and string limits.
- Kept URL validation local and network-free; no Gemini, provider, prompt, extraction, or evidence-search logic was added.

## Tests

- Added coverage for complete and minimal profiles, whitespace rejection, every configured profile list limit, and unknown fields.
- Added coverage for valid, empty, and overlong candidate claims.
- Added HTTP/HTTPS evidence URL coverage plus malformed, non-HTTP, relative, and credential-bearing rejection.
- Added required excerpt and explicit source-type validation.
- Added supported, insufficient-evidence, and assumption mappings, the supported-evidence invariant, confidence enum/reason validation, nested extra-field rejection, evidence-list limits, and deterministic JSON serialization.

## Failures and iterations

No test or implementation repair iteration was required. The focused schema suite and complete backend suite passed on their first runs.

## Final verification

- `.\\.venv\\Scripts\\python.exe -m pytest tests/test_domain_schemas.py -q` — passed with 31 tests in 0.21 seconds.
- `.\\.venv\\Scripts\\python.exe -m pytest -q` — passed with 92 tests in 1.46 seconds.
- `.\\.venv\\Scripts\\python.exe -m pip check` — passed with `No broken requirements found.`
- `.\\.venv\\Scripts\\python.exe -m compileall -q main.py guardrails schemas services tests` — passed.

## Final Result

All Task 3 acceptance criteria were satisfied. Strict bounded brand and evidence contracts exist, candidate claims remain distinct from support decisions, evidence sources preserve URLs and excerpts, uncertain states can remain evidence-free, unknown output fields are rejected, and validation performs no network access.

### Human Review Hardening

Human review identified that evidence-reference URL validation was locally syntactic but did not reuse the existing non-resolving public-reference safety boundary.

#### Finding

- `EvidenceReference` rejected malformed, non-HTTP, relative, and credential-bearing URLs, but localhost and literal non-public IP references could still be retained as syntactically valid evidence URLs.

#### Manual change

- Reused the existing non-resolving `validate_url_reference()` guardrail for evidence URLs.
- Evidence-reference validation remains network-free and performs no DNS lookup.
- Localhost and literal non-global/private IP references are now rejected consistently with the existing AnswerLens reference-validation boundary.
- No fetching behavior or SSRF/network path was introduced into the schema layer.

#### Tests added

- Added coverage rejecting:
  - `http://localhost/source`
  - `http://127.0.0.1/source`
  - `http://10.0.0.5/source`

#### Human-review iterations

- The first manual edit left the removed `TypeAdapter` implementation line in place, producing a collection-time `NameError`; the stale line was removed.
- The first placement of the new parametrized test interrupted an existing parametrized decorator/function pair, producing a Pytest collection error; the test was moved into the evidence-URL test section.
- After those manual corrections, the focused and complete suites passed.

#### Final human-review verification

- `.\.venv\Scripts\python.exe -m pytest tests/test_domain_schemas.py -q` — 34 passed.
- `.\.venv\Scripts\python.exe -m pytest -q` — 95 passed.
- `.\.venv\Scripts\python.exe -m pip check` — No broken requirements found.
- `.\.venv\Scripts\python.exe -m compileall -q main.py guardrails schemas services tests` — passed.
- `git diff --check` — passed; only Windows LF/CRLF conversion warnings were reported.

## Human Review

- [x] Domain schemas reviewed.
- [x] Validation and evidence semantics reviewed.
- [x] Test results reviewed.
- [x] Repository diff reviewed before commit.


# Task 4 — Gemini Structured-Output Provider

## Goal

Introduce a reusable asynchronous Gemini provider that requests structured output and validates every response against application-owned Pydantic models without implementing Brand Intelligence or other later agent behavior.

## Implementation

- Added a generic asynchronous `StructuredOutputProvider` protocol.
- Added `GeminiStructuredOutputProvider` using the official Google Gen AI SDK.
- Configured the project-selected `gemini-2.5-flash` model.
- Added environment-based `GEMINI_API_KEY` configuration for real provider construction.
- Added injected-client support so automated tests require neither an API key nor network access.
- Configured structured JSON responses using the caller-supplied Pydantic response model.
- Added application-side `model_validate_json()` validation after generation.
- Added explicit configuration, request, and structured-output errors.
- Bounded invalid structured-output recovery to two total generation attempts.
- API/request failures fail immediately rather than entering the malformed-output retry path.
- Added `google-genai==2.18.1`.
- Updated Pydantic from `2.11.7` to `2.12.5` for SDK dependency compatibility.

## Iterations / Failures

- Initial dependency installation failed because the selected Google Gen AI SDK version required Pydantic `>=2.12.5`; the Pydantic pin was updated and existing tests remained green.
- The first focused provider run passed but produced a Pytest collection warning because a fixture model was named `TestOutput`; it was renamed and the warning disappeared.
- One version-report command used the wrong working-directory-relative virtual-environment path; it was rerun successfully from `backend`.

## Verification

- Focused Gemini provider tests — 14 passed.
- Complete backend suite — 109 passed.
- `python -m pip check` — no broken requirements.
- `python -m compileall -q main.py agents graph guardrails providers schemas services tests` — passed.
- `git diff --check` — passed.
- Installed versions confirmed `google-genai==2.18.1` and `pydantic==2.12.5`.
- No real Gemini API request was made during automated verification.

## Final Result

Task 4 established a reusable typed Gemini boundary with application-side validation, bounded malformed-output retries, explicit error handling, environment-only credential configuration, and fully mocked automated tests. Product-specific brand extraction remains deferred.

## Human Review

- [x] Gemini provider implementation reviewed.
- [x] Structured-output validation and retry behavior reviewed.
- [x] Provider tests and dependency changes reviewed.
- [x] Repository diff reviewed before commit.


# Task 5 — Brand Intelligence Agent

## Goal

Implement the Brand Intelligence extraction stage that transforms previously collected crawl and machine-readable evidence into the existing validated `BrandProfile` contract without performing claim verification or later GEO analysis.

## Implementation

- Added `backend/agents/brand_agent.py` as the focused Brand Intelligence layer.

- Added deterministic evidence preparation from an existing `CrawlResult` and `MachineReadableAudit`.

- Included only successful crawl pages as usable website evidence; failed crawl records are excluded.

- Preserved requested and final source URLs, page titles, meta descriptions, headings, and readable page content within explicit bounds.

- Added stable `page_N` source labels based on deterministic successful-page ordering.

- Added bounded publisher-provided machine-readable observations, including `llms.txt` title/summary where present, structured-data types, and structured-data source pages.

- Kept malformed structured data from being promoted to valid structured evidence.

- Explicitly labeled `llms.txt`, JSON-LD, crawled page content, metadata, headings, and other publisher-provided material as untrusted data rather than independent verification.

- Added prompt instructions that source content is evidence rather than instructions, prompt-injection attempts inside source material must be ignored, outside knowledge must not be used, and unsupported facts must not be invented.

- Added optional user-supplied business-category context without treating it as independent website evidence.

- Added normalization, length bounding, JSON serialization, and a separately delimited `USER-SUPPLIED CONTEXT (UNTRUSTED DATA)` block for category input.

- Explicitly instructed the model to treat user-supplied category context as data rather than instructions.

- Used the application-facing `StructuredOutputProvider` abstraction and requested the existing `BrandProfile` Pydantic contract.

- Kept the agent independent from Gemini-specific SDK/configuration code and reused Task 4 provider-level structured-output retry behavior.

- Added explicit `BrandIntelligenceError` behavior when no successful crawl evidence exists.

- Preserved provider failures instead of generating a fallback or fabricated `BrandProfile`.

- Kept generated `BrandClaim` values as unverified propositions. No `ClaimEvidence`, support status, evidence confidence, or claim verification was added.

## Evidence Bounds

- Maximum successful website pages included: 8

- Maximum readable page content: 4,000 characters per page

- Maximum headings: 12 per page

- Maximum heading length: 200 characters

- Maximum meta-description length: 500 characters

- Maximum `llms.txt` title length: 300 characters

- Maximum `llms.txt` summary length: 1,000 characters

- Maximum structured-data types included: 40

- Maximum total prepared evidence length: 40,000 characters

- Optional category length reuses the existing domain-schema category bound

Evidence truncation is deterministic. No preliminary LLM summarization or random evidence sampling is performed.

## Tests

- Added `backend/tests/test_brand_agent.py`.

- Added coverage for successful typed extraction and confirmation that the provider is asked for `BrandProfile`.

- Added coverage for requested/final source URLs, title, metadata, headings, readable content, stable page labels, and deterministic evidence preparation.

- Added coverage ensuring failed crawl pages are excluded and an all-failed crawl prevents the provider from being called.

- Added coverage for page count, content, heading, metadata, structured-data, `llms.txt`, and total evidence bounds.

- Added coverage for missing `llms.txt` and malformed structured data.

- Added prompt-boundary tests covering untrusted source content, prompt injection, outside knowledge, unsupported invention, and unverified candidate-claim semantics.

- Added optional-category tests for absent input, normalization, length bounds, untrusted-context labeling, and newline/quote injection attempts.

- Added provider-failure coverage confirming no fallback profile is returned.

- Added a regression check confirming that the Brand Intelligence module does not depend directly on `GeminiStructuredOutputProvider` or `genai`.

## Human Review Hardening

Human review identified that the initial user-supplied business-category context was bounded and labeled as user context but was inserted into the prompt without the same explicit untrusted-data boundary applied to crawled website evidence.

### Finding

- A category value containing line breaks or instruction-like text could be interpolated directly into the prompt as plain text outside the website-evidence block.

### Manual change

- Normalized category whitespace deterministically.

- Retained the existing category length bound.

- Serialized the category value using JSON string encoding.

- Added explicit `BEGIN USER-SUPPLIED CONTEXT` and `END USER-SUPPLIED CONTEXT` delimiters.

- Labeled the block `USER-SUPPLIED CONTEXT (UNTRUSTED DATA)`.

- Added an extraction rule instructing the model to treat user-supplied context only as data and never as instructions.

### Human-review iterations

- After the category-boundary implementation was hardened, the focused Task 5 suite initially produced 14 passing tests and 2 failures.

- Both failures were existing category-prompt assertions that still expected the previous unquoted category representation.

- The tests were updated to assert the new JSON-serialized, untrusted-context representation.

- Added a regression test containing newline-separated instruction-like text and embedded quotes to verify that category input remains inside the serialized user-context boundary.

- The focused suite then passed with 17 tests.

## Final Verification

- `.\.venv\Scripts\python.exe -m pytest tests/test_brand_agent.py -q` — passed with 17 tests in 0.50 seconds.

- `.\.venv\Scripts\python.exe -m pytest -q` — passed with 126 tests in 1.99 seconds.

- Both Pytest runs emitted a non-blocking `PytestCacheWarning` because Windows denied creation of `backend/.pytest_cache`; test execution itself completed successfully.

- `.\.venv\Scripts\python.exe -m pip check` — passed with `No broken requirements found.`

- `.\.venv\Scripts\python.exe -m compileall -q main.py agents guardrails providers schemas services tests` — passed.

- `git diff --check` — passed with no reported whitespace errors.

## Final Result

Task 5 established the Brand Intelligence extraction stage. Existing crawl and machine-readable evidence can now be transformed into a validated `BrandProfile` through the reusable structured-output provider while preserving deterministic evidence bounds, source attribution, explicit untrusted-data boundaries, and failure visibility. Candidate claims remain deliberately unverified for the next Claim Evidence Map stage.

## Human Review

- [x] Brand Intelligence implementation reviewed.

- [x] Evidence preparation and prompt trust boundaries reviewed.

- [x] Focused and complete backend test results reviewed.

- [ ] Repository diff reviewed before commit.