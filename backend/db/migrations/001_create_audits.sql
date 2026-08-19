CREATE TABLE IF NOT EXISTS audits (
    id UUID PRIMARY KEY,
    target_url TEXT NOT NULL,
    category TEXT,
    known_competitors JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    previous_audit_id UUID REFERENCES audits(id),
    result JSONB,
    delta JSONB,
    error_code TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS audits_target_url_idx ON audits(target_url);
CREATE INDEX IF NOT EXISTS audits_previous_audit_id_idx ON audits(previous_audit_id);
CREATE INDEX IF NOT EXISTS audits_created_at_idx ON audits(created_at DESC);
