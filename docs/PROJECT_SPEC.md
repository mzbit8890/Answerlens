# AnswerLens — Finalized Build Specification

## 1. Product

**AnswerLens — AI Brand Evidence & GEO Readiness Agent**

### One-line description

AnswerLens is an autonomous GEO audit agent that determines whether enough publicly discoverable evidence exists for AI answer engines to confidently understand and recommend a business, identifies where that evidence breaks down, compares the brand with competitors, proposes measurable improvements, and measures whether those improvements work.

---

# 2. Core Goal

A user enters a company's website.

AnswerLens will:

1. Crawl and understand the company.
2. Inspect its AI-readable and machine-readable information.
3. Build a structured Brand Evidence Profile.
4. Separate supported claims from assumptions.
5. Generate realistic recommendation questions.
6. Search the web for independent evidence and competitors.
7. Evaluate how well-supported the brand is for each question.
8. Automatically gather more evidence when confidence is insufficient.
9. Explain exactly why the brand is strong or weak.
10. Suggest evidence-backed GEO experiments.
11. Save the audit as a baseline.
12. Allow the audit to be rerun later.
13. Measure what improved or became worse.

The project does **not** claim to reproduce exactly what ChatGPT, Claude, Gemini or Perplexity will answer.

Instead:

> **AnswerLens performs controlled, web-grounded evaluations of the evidence available to answer engines.**

---

# 3. User Input

The first screen contains:

### Required

**Company website**

Example:

`https://linear.app`

### Optional

**Business category**

Example:

`Project Management Software`

### Optional

**Known competitors**

Example:

`Jira, Asana, ClickUp`

### Main action

**Run Evidence Audit**

---

# 4. Agent Workflow

The core LangGraph workflow is:

```text
START
   ↓
validate_target
   ↓
crawl_evidence
   ↓
inspect_machine_readable_surfaces
   ↓
extract_brand_profile
   ↓
build_claim_evidence_map
   ↓
generate_recommendation_queries
   ↓
retrieve_external_evidence
   ↓
run_grounded_query_evaluations
   ↓
enough_confidence?
   ├── NO
   │     ↓
   │  plan_targeted_research
   │     ↓
   │  retrieve_more_evidence
   │     ↓
   │  re_evaluate_changed_queries
   │     ↓
   │  enough_confidence?
   │     ↓
   │  max 2 additional research rounds
   │
   └── YES / research limit reached
         ↓
      diagnose_evidence_gaps
         ↓
      generate_experiments
         ↓
      calculate_metrics
         ↓
      complete_execution_trace
         ↓
      save_audit
         ↓
      compare_previous_audit
         ↓
        END

```

Website discovery is handled inside the bounded crawl stage rather than represented as a separate LangGraph node.

The confidence decision is application-owned. Completed evaluations with low confidence may trigger additional evidence gathering; medium/high confidence stops research regardless of readiness. Provider-unavailable evaluations do not enter the evidence-research loop.

`save_audit` and `compare_previous_audit` are completed in the final persistence/product stage.

This is a real conditional agent workflow rather than a fixed sequence of LLM calls.

---


# 5. Website Crawler

AnswerLens will crawl up to **8 useful pages**, not the entire website.

Prioritize:

* Homepage
* Product/features
* Pricing
* About
* Documentation
* FAQ
* Use cases
* Customer/case-study pages
* Relevant category pages

The crawler will extract:

* Main page content
* Headings
* Page title
* Meta description
* Links
* Structured data
* Source URL

It will remove irrelevant navigation, cookie text and obvious boilerplate where possible.

---

# 6. AI / Machine-Readable Surface Audit

AnswerLens will also inspect:

* `/llms.txt`
* `robots.txt`
* `sitemap.xml`
* JSON-LD
* Schema.org markup
* Organization schema
* Product/software schema
* FAQ schema
* Documentation structure
* Machine-readable product information

Important:

**The application will NOT claim that having `llms.txt` automatically improves AI rankings or citations.**

It is treated as one discoverability/readability signal among many.

That demonstrates engineering judgment instead of blindly treating every GEO tactic as a ranking factor.

---

# 7. Brand Intelligence Agent

The agent turns crawled content into validated structured data.

Example:

```json
{
  "brand": "Linear",
  "category": "Project Management Software",
  "audiences": [
    "software teams",
    "product teams"
  ],
  "capabilities": [
    "issue tracking",
    "project planning",
    "roadmaps"
  ],
  "use_cases": [],
  "positioning": "...",
  "claims": []
}
```

Every LLM response is validated using Pydantic.

Malformed responses are rejected or retried.

---

# 8. Brand Evidence Map

This is a major feature.

AnswerLens will distinguish between:

**what is actually supported**

and

**what the model merely thinks might be true.**

Example:

```text
CLAIM
Linear provides issue tracking.

EVIDENCE
https://linear.app/product

CONFIDENCE
HIGH
```

Versus:

```text
CLAIM
Linear is designed specifically for marketing agencies.

EVIDENCE
No strong evidence found.

CONFIDENCE
LOW
```

Each evidence record contains:

* Claim
* Evidence URL
* Evidence excerpt
* Source type
* Confidence
* Reason for confidence

Unsupported claims cannot silently become facts.

---

# 9. Query Intelligence Agent

Generate approximately **12 realistic recommendation queries**.

Queries should cover several intents.

### Category discovery

`Best project management tools for engineering teams`

### Alternative/comparison

`Best Jira alternatives`

### Audience/use case

`Project management software for startups`

### Problem-driven

`Best tools for distributed engineering teams`

### Capability-driven

`Best issue tracking tools for software development`

The queries should be generated from the actual brand profile rather than from a static template.

---

# 10. External Evidence Retrieval

Use Tavily Search API.

For each query retrieve a controlled number of results.

Capture:

* Search result URL
* Domain
* Title
* Relevant content
* Brands mentioned
* Competitors found
* Independent evidence
* Brand-owned evidence

AnswerLens should distinguish:

**brand-owned evidence**

from

**independent third-party evidence.**

---

# 11. Controlled Recommendation Evaluation

For each query, Gemini receives the retrieved evidence and performs a **grounded evaluation**.

It answers:

* Is there enough evidence to support mentioning this brand?
* What evidence supports it?
* What evidence is missing?
* Which competitors have stronger evidence?
* How confident is the evaluation?

Example:

```text
QUERY
Best project management tools for remote engineering teams

BRAND
Linear

READINESS
Medium

WHY

Strong evidence exists for:
- software development
- issue tracking
- product teams

Weak evidence exists for:
- explicit remote-team workflows

Competitors with stronger evidence:
- ClickUp
- Asana

CONFIDENCE
High
```

This does **not** mean:

“ChatGPT has a 63% probability of mentioning Linear.”

AnswerLens measures **evidence readiness**, not proprietary model ranking probabilities.

---

# 12. Autonomous Evidence-Gathering Loop

The agent does not automatically gather more evidence merely because readiness is low. Additional research is triggered when evaluation confidence is insufficient.

If confidence is below the threshold:

```text
confidence < threshold
        ↓
identify missing evidence
        ↓
generate targeted search
        ↓
retrieve more sources
        ↓
re-evaluate
```

Maximum:

**2 additional evidence-gathering attempts.**

This creates a genuine autonomous reasoning loop.

---

# 13. Evidence Gap Agent

This is the main “wow” feature.

For every weak query, show:

### Query

Best project management software for agencies

### Readiness

Low

### Why

1. Strong evidence establishes the product for software teams.
2. Explicit agency positioning is weak.
3. Competing brands repeatedly appear around agency workflows.
4. Competitors have dedicated content addressing this intent.

### Supporting sources

Actual URLs.

### Confidence

High

### Suggested experiment

Create or strengthen explicit evidence around agency workflows and rerun this query cluster.

---

# 14. GEO Experiment Agent

Recommendations must never simply say:

> “Write more content.”

Every recommendation follows:

```text
OBSERVATION
        ↓
HYPOTHESIS
        ↓
PROPOSED CHANGE
        ↓
EVALUATION QUERIES
        ↓
SUCCESS CONDITION
```

Example:

### Observation

Remote engineering relevance is implicit but weak.

### Hypothesis

Answer engines have insufficient explicit evidence connecting the product with distributed engineering workflows.

### Experiment

Strengthen one dedicated page explaining remote/distributed engineering workflows.

### Re-evaluate

* best PM software for remote engineering
* tools for distributed developers
* project management for remote software teams

### Success condition

Query readiness increases and additional supported evidence appears during the next audit.

---

# 15. Baseline → Rerun → Delta

Every completed audit becomes a baseline.

Example:

### Audit #1

```text
Evidence Coverage       61%
Query Readiness         54%
Strong Queries          4 / 12
Weak Queries            5 / 12
Evidence Gaps           7
```

After changes are made, the company can run AnswerLens again.

### Audit #2

```text
Evidence Coverage       76%   +15
Query Readiness         69%   +15
Strong Queries          8 / 12  +4
Weak Queries            2 / 12  -3
Evidence Gaps           4       -3
```

This proves:

**measure → change → rerun → evaluate**

instead of simply producing AI recommendations.

---

# 16. Metrics

The dashboard should focus on approximately five meaningful metrics.

### Evidence Coverage

How much of the important brand positioning is backed by explicit evidence.

### Query Readiness

How strongly the brand can be supported across generated recommendation queries.

### Strong Queries

Queries where evidence strongly supports the brand.

### Evidence Gaps

Important intents with incomplete evidence.

### External Evidence Diversity

How many independent sources support relevant claims.

Do not invent a fake “ChatGPT ranking score.”

---

# 17. Agent Execution Trace

The recruiter should be able to see what the agent actually did.

Example:

```text
✓ Validated target website

✓ Crawled 8 useful pages

✓ Inspected llms.txt, sitemap and structured data

✓ Extracted 21 brand claims

✓ Verified 16 claims with direct evidence

✓ Generated 12 recommendation queries

✓ Reviewed 47 external search results

✓ Discovered 6 competing brands

↻ 2 queries required additional research

✓ Identified 5 evidence gaps

✓ Generated 4 measurable experiments

✓ Audit complete
```

Each step should include status and optionally duration.

---

# 18. Four Final Screens

Keep the application focused.

## Screen 1 — New Audit

Website, category and optional competitors.

---

## Screen 2 — Audit Overview

Show:

* Evidence Coverage
* Query Readiness
* Strong queries
* Evidence gaps
* External sources
* Strongest positioning
* Weakest positioning
* Machine-readable surface status
* Agent execution trace

---

## Screen 3 — Query Explorer

Table:

| Query                            | Readiness | Evidence | Confidence |
| -------------------------------- | --------- | -------- | ---------- |
| Best tools for engineering teams | High      | Strong   | High       |
| Jira alternatives                | High      | Strong   | High       |
| PM software for agencies         | Low       | Weak     | High       |
| PM tools for remote teams        | Medium    | Partial  | Medium     |

Clicking a row opens:

### Explain this evidence gap

with reasoning, evidence, competitors, sources and confidence.

---

## Screen 4 — Experiments & Progress

Show prioritized experiments.

Each experiment includes:

* Problem
* Evidence
* Hypothesis
* Proposed change
* Queries affected
* Success criteria
* Confidence

If a previous audit exists, show:

**Previous vs Current**

with improvements and regressions.

---

# 19. Guardrails

This is extremely important.

Use explicit limits such as:

```text
MAX_CRAWL_PAGES = 8

MAX_QUERIES = 12

MAX_RESULTS_PER_QUERY = 5

MAX_RESEARCH_RETRIES = 2

MAX_EXPERIMENTS = 6

AUDIT_TIMEOUT = 120 seconds
```

Additional safeguards:

* Only HTTP/HTTPS URLs
* Block localhost/private-network URLs
* URL validation
* Request timeouts
* Response-size limits
* Crawl rate limits
* Deduplicate pages
* Deduplicate evidence
* Treat crawled text as untrusted data
* Ignore instructions embedded inside websites
* Validate every LLM response
* Require sources for evidence-backed findings
* Unsupported claims remain unsupported
* Never fabricate URLs
* Never allow unlimited agent loops
* Gracefully handle Gemini/Tavily failures

---

# 20. Database

Use:

**PostgreSQL — Neon**

Core tables:

```text
audits

crawled_pages

brand_profiles

claims

queries

sources

query_findings

experiments

agent_events
```

This allows audit history and baseline comparisons.

---

# 21. Final Technology Stack

## Development

**VS Code**

## Coding Agent

**Codex**

Used for real repository tasks with human review.

## Frontend

* Next.js
* React
* TypeScript
* Tailwind CSS

## Node.js

Use Next.js Route Handlers / server-side Node runtime as the frontend/backend boundary where appropriate.

## AI Backend

* Python
* FastAPI

## Agent Orchestration

**LangGraph**

## LLM

**Gemini 3.6 Flash**

## Search

**Tavily Search API**

## Crawling

* httpx
* BeautifulSoup

## Validation

**Pydantic**

## Database

**PostgreSQL / Neon**

## Backend Testing

**Pytest**

## Frontend Testing

A small number of meaningful component/integration tests.

## Version Control

**Git + GitHub**

## Deployment

* Frontend → Vercel
* FastAPI → Render
* PostgreSQL → Neon

---

# 22. APIs Used

Use only two external AI/data APIs:

```text
GEMINI_API_KEY=

TAVILY_API_KEY=

DATABASE_URL=
```

Gemini performs:

* Brand extraction
* Structured reasoning
* Query generation
* Evidence evaluation
* Gap diagnosis
* Experiment generation

Tavily performs:

* External web search
* Competitor discovery
* Source retrieval

---

# 23. What We Intentionally Do NOT Use

Do not add:

* OpenAI API
* Anthropic API
* Perplexity API
* Claude API
* Pinecone
* Redis
* MongoDB
* Supabase
* Separate vector database
* Kafka
* Celery
* Authentication
* Payments
* User management
* Massive crawling
* Automated content publishing
* Huge multi-agent swarms

None are necessary to prove the core engineering capability.

---

# 24. Why No Redis

Redis would currently solve a problem AnswerLens does not yet have.

The demo does not require:

* thousands of concurrent audits
* distributed workers
* cross-server queues
* heavy caching
* shared sessions
* high-throughput job processing

Adding Redis simply to make the architecture look larger would increase operational complexity without making the GEO agent more intelligent.

The architecture can be made queue-ready so Redis can be introduced later if background distributed processing becomes necessary.

That demonstrates better engineering judgment than adding infrastructure for the sake of a technology checklist.

---

# 25. Coding-Agent Evidence

The repository should contain:

```text
AGENTS.md

docs/
   ARCHITECTURE.md
   EVALS.md
   GEO_ASSUMPTIONS.md
   AGENT_WORKFLOW.md
   CODING_AGENT_RUNS.md
```

`CODING_AGENT_RUNS.md` should contain several genuine examples.

Example:

```text
TASK

Implement crawler validation and tests.

COMPLETION CRITERIA

- Maximum 8 pages
- Private IPs rejected
- Request timeout implemented
- Duplicate URLs removed
- All crawler tests pass

CODING AGENT

Codex

RESULT

Initial implementation:
8/11 tests passed.

Iteration:
Agent inspected failures and corrected URL normalization.

FINAL RESULT

11/11 tests passed.

HUMAN REVIEW

Reviewed diff manually.
Changed timeout handling before merge.
```

Include only things that really happened.

Never claim an overnight autonomous run if one was not actually performed.

---

# 26. How Codex Should Be Used During Development

Do not ask Codex:

> Build AnswerLens.

Instead decompose the work.

### Codex task 1

Crawler + safety guardrails.

### Codex task 2

Pydantic schemas + structured LLM responses.

### Codex task 3

LangGraph evidence workflow.

### Codex task 4

Tests for malformed AI output and retrieval failures.

### Codex task 5

Fix-until-green testing loop.

For at least one stage, run two independent tasks in parallel if your available Codex usage allows it.

Then manually:

* inspect every diff
* understand every change
* reject bad shortcuts
* run tests
* modify code when necessary

This demonstrates **coding-agent engineering**, rather than merely copying generated code.

---

# 27. Repository Structure

```text
answerlens/
│
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   ├── types/
│   └── tests/
│
├── backend/
│   ├── api/
│   ├── agents/
│   │   ├── brand_agent.py
│   │   ├── query_agent.py
│   │   ├── evidence_agent.py
│   │   └── experiment_agent.py
│   ├── graph/
│   ├── providers/
│   │   ├── base.py
│   │   └── gemini.py
│   ├── services/
│   │   ├── crawler.py
│   │   ├── search.py
│   │   └── structured_data.py
│   ├── models/
│   ├── schemas/
│   ├── guardrails/
│   └── tests/
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── EVALS.md
│   ├── GEO_ASSUMPTIONS.md
│   ├── AGENT_WORKFLOW.md
│   └── CODING_AGENT_RUNS.md
│
├── AGENTS.md
├── README.md
└── .env.example
```

---

# 28. Final Definition of Done

AnswerLens is ready for the application when a recruiter can:

1. Open the live application.
2. Enter a real company website.
3. Start an audit.
4. Watch an agent execution trace.
5. See a structured understanding of the company.
6. See claims tied to actual evidence.
7. See approximately 12 realistic recommendation queries.
8. See independent sources and competing brands.
9. Open a query and understand exactly why evidence is strong or weak.
10. See the autonomous agent gather additional evidence when necessary.
11. Receive concrete GEO experiments instead of generic AI suggestions.
12. Rerun the website and measure change.
13. Open GitHub and see clean architecture, tests, guardrails and documentation.
14. See genuine evidence that Codex was used through goal → acceptance criteria → implementation → testing → human review loops.

## Final product statement

> **AnswerLens is an agentic GEO evidence auditor that crawls a company's public web presence, builds a source-backed model of what the brand can credibly claim, generates realistic recommendation intents, investigates independent web evidence and competitors, autonomously resolves evidence gaps, evaluates recommendation readiness, proposes measurable GEO experiments, and tracks whether those experiments improve the brand's evidence over time.**
