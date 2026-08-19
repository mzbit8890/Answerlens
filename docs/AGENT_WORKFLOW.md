# Agent Workflow

## Overview

AnswerLens runs a bounded LangGraph workflow for source-grounded GEO evidence analysis. It collects publisher and external evidence, validates model-produced structures and citations, evaluates recommendation-query readiness, and produces deterministic metrics and a bounded execution trace.

## Workflow

```text
validate_target
  → crawl_evidence
  → inspect_machine_readable_surfaces
  → extract_brand_profile
  → build_claim_evidence_map
  → generate_recommendation_queries
  → retrieve_external_evidence
  → run_grounded_query_evaluations
  → conditional confidence route
      → optional plan_targeted_research
      → retrieve_more_evidence
      → re_evaluate_changed_queries
  → diagnose_evidence_gaps
  → generate_geo_experiments
  → calculate_metrics
  → complete_execution_trace
```

Targeted research is limited to two additional rounds. Only completed evaluations with low confidence may trigger more research. Medium- or high-confidence evaluations stop research, and provider-unavailable evaluations do not enter the research loop.

## External boundaries

- Gemini is accessed through the application-owned `StructuredOutputProvider` interface.
- Tavily is accessed through the application-owned `SearchProvider` interface.
- Website access passes through the crawler's URL, network, redirect, timeout, and response-size safety boundary.
- PostgreSQL persistence occurs at the product/service layer around workflow execution.

These interfaces support dependency injection for deterministic verification while production uses the configured Gemini, Tavily, and PostgreSQL adapters. Test doubles are not production providers.

## Grounding

- Website and source content is untrusted data, never executable instructions.
- Structured model output is validated with application-owned Pydantic schemas.
- Evidence URLs, source ownership, and excerpts are validated by application code.
- Unsupported claims remain explicitly unsupported.
- External evidence remains attributed to its source.
- AnswerLens does not fabricate evidence URLs.
- AnswerLens measures evidence readiness, not a proprietary answer-engine ranking probability.

## Bounds

- `MAX_CRAWL_PAGES = 8`
- `MAX_QUERIES = 12`
- `MAX_RESULTS_PER_QUERY = 5`
- `MAX_RESEARCH_RETRIES = 2`
- `MAX_EXPERIMENTS = 6`
- `AUDIT_TIMEOUT = 120 seconds`

## Execution trace

Each audit produces an application-owned, bounded execution trace covering the major workflow stages. The trace makes completed work, conditional research, and explicit failure states visible without exposing prompts, credentials, or raw provider payloads.
