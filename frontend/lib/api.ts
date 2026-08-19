import type { AuditInput, AuditRecord } from "@/types/audit";
const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
export class ApiError extends Error { constructor(message: string, public status: number, public audit?: AuditRecord) { super(message); } }
async function request<T>(path: string, init?: RequestInit): Promise<T> { let response: Response; try { response = await fetch(`${API_BASE}${path}`, { ...init, headers: { "Content-Type": "application/json", ...init?.headers } }); } catch { throw new ApiError("The AnswerLens API is unreachable. Check the backend configuration and try again.", 0); } const body = await response.json().catch(() => null); if (!response.ok) { const detail = body?.detail; throw new ApiError(detail?.message || "The request could not be completed.", response.status, detail?.audit); } return body as T; }
export const createAudit = (input: AuditInput) => request<AuditRecord>("/audits", { method: "POST", body: JSON.stringify(input) });
export const getAudit = (id: string) => request<AuditRecord>(`/audits/${encodeURIComponent(id)}`, { cache: "no-store" });
export const rerunAudit = (id: string) => request<AuditRecord>(`/audits/${encodeURIComponent(id)}/rerun`, { method: "POST" });
export function normalizeCompetitors(value: string): string[] { const seen = new Set<string>(); return value.split(/[,\n]/).map(item => item.trim()).filter(item => { const key = item.toLocaleLowerCase(); if (!item || seen.has(key)) return false; seen.add(key); return true; }).slice(0, 10); }
