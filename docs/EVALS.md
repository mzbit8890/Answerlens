# Evaluations

## Evaluation philosophy

AnswerLens evaluates the quality and readiness of available evidence. It does not claim to reproduce or predict rankings from ChatGPT, Claude, Gemini, Perplexity, or another proprietary answer engine.

## Core metrics

- **Evidence Coverage** measures how much of the candidate brand-claim set has explicit supporting evidence.
- **Query Readiness** summarizes grounded readiness across the generated recommendation queries.
- **Strong Queries** counts queries whose evidence supports a high-readiness evaluation.
- **Evidence Gaps** counts diagnosed intents where relevant support is incomplete or absent.
- **External Evidence Diversity** measures the diversity of attributed external sources supporting the evaluation set.

These are application evidence metrics, not a "ChatGPT score" or a model-ranking probability.

## Query evaluation

Each query uses explicit low, medium, or high readiness and low, medium, or high confidence. `unavailable` remains a separate provider or retrieval state rather than being treated as weak evidence. Medium and high readiness require supporting external evidence; low readiness may be grounded in an observed lack of external support. User-supplied known competitors remain hints until retrieved external evidence supports their inclusion.

## Evidence validation

Application code validates source URLs, source ownership, quoted excerpts, exact query identity, competitor evidence, claim grounding, and structured model output. Schema-valid output is still rejected when it violates these semantic grounding rules.

## Autonomous research evaluation

Only low-confidence completed query evaluations may enter targeted research. Research planning, retrieval, and selective re-evaluation are bounded to a maximum of two additional rounds. Medium/high-confidence and unavailable evaluations do not create an unbounded retry loop.

## Baseline and rerun evaluation

Completed reruns are compared deterministically across Evidence Coverage, Query Readiness, Strong Queries, Evidence Gaps, and External Evidence Diversity. Deltas use current minus previous values; for Evidence Gaps, a lower count is interpreted as improvement.

## Automated verification

- The complete backend suite passes with 246 tests.
- A successful offline end-to-end integration exercises the real production LangGraph and application workflow.
- Only true external or nondeterministic boundaries are replaced with deterministic injected substitutes in that integration test.
- Production has no `TEST_MODE` switch and does not emit fake completed-audit results.
