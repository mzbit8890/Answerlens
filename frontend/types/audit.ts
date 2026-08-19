export type Level = "low" | "medium" | "high";
export type AuditStatus = "running" | "completed" | "failed";
export type Direction = "improved" | "regressed" | "unchanged";
export interface Evidence { url: string; excerpt: string; source_type?: string; source_ownership?: "brand_owned" | "independent" }
export interface ClaimEvidence { claim: { statement: string }; support_status: string; evidence: Evidence[]; confidence: Level; confidence_reason: string }
export interface Query { query: string; intent: string; rationale: string }
export interface CompetitorEvidence { competitor: string; evidence: Evidence[]; reason: string }
export interface Evaluation { query: string; status: "completed" | "unavailable"; readiness: Level | null; supporting_evidence: Evidence[]; missing_evidence: string[]; competitor_evidence: CompetitorEvidence[]; confidence: Level | null; reason: string | null }
export interface Gap { query: string; readiness: Level; why: string; missing_evidence: string[]; supporting_sources: Evidence[]; stronger_competitors: CompetitorEvidence[]; confidence: Level }
export interface Experiment { observation: string; hypothesis: string; proposed_change: string; evaluation_queries: string[]; success_condition: string; confidence: Level }
export interface Metrics { evidence_coverage: number; query_readiness: number; strong_queries: number; evidence_gaps: number; external_evidence_diversity: number; completed_evaluations: number; unavailable_evaluations: number }
export interface MetricDelta { previous: number; current: number; delta: number; direction: Direction }
export interface AuditDelta { evidence_coverage: MetricDelta; query_readiness: MetricDelta; strong_queries: MetricDelta; evidence_gaps: MetricDelta; external_evidence_diversity: MetricDelta; new_gap_queries: string[]; resolved_gap_queries: string[] }
export interface AuditResult { target_url: string; brand_profile: { brand: string; category: string | null; audiences: string[]; capabilities: string[]; use_cases: string[]; positioning: string | null }; claim_evidence_map: { records: ClaimEvidence[] }; machine_readable: { robots_status: string; sitemap_status: string; sitemap_urls_discovered: number; llms_txt_status: string; llms_txt_links_discovered: number; structured_data_status: string; structured_data_pages: number; structured_data_types: string[] }; query_set: { queries: Query[] }; query_evaluations: { evaluations: Evaluation[] }; evidence_gaps: { gaps: Gap[] }; experiments: { experiments: Experiment[] }; metrics: Metrics; execution_trace: { stage: string; status: string; message: string; duration_ms: number; counters: Record<string, number> }[]; research_rounds: unknown[] }
export interface AuditRecord { id: string; target_url: string; category: string | null; known_competitors: string[]; status: AuditStatus; previous_audit_id: string | null; result: AuditResult | null; delta: AuditDelta | null; error_code: string | null; error_message: string | null; created_at: string; completed_at: string | null }
export interface AuditInput { target_url: string; category?: string; known_competitors: string[] }
