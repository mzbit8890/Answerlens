import Link from "next/link"; import type { ReactNode } from "react";
export function Shell({ children }: { children: ReactNode }) { return <><header className="topbar"><Link href="/" className="brand"><span className="lens">A</span>AnswerLens</Link><span className="tagline">Evidence-grounded GEO intelligence</span></header><main className="shell">{children}</main></>; }
export function Badge({ value }: { value: string | null }) { return <span className={`badge badge-${value || "unavailable"}`}>{(value || "unavailable").replaceAll("_", " ")}</span>; }
export function SourceLink({ url, children }: { url: string; children?: ReactNode }) { return <a href={url} target="_blank" rel="noopener noreferrer" className="source-link">{children || url}</a>; }
