-- One vocabulary for document kinds (card1 forms come in Russian, Uzbek Cyrillic or Latin)
-- and a human-readable title; both are filled by the index writer.
ALTER TABLE documents RENAME COLUMN short_title TO display_title;
ALTER TABLE documents ADD COLUMN doc_kind text NOT NULL DEFAULT 'boshqa';
DROP INDEX IF EXISTS documents_type_status;
CREATE INDEX documents_kind_status ON documents (doc_kind, status);
CREATE INDEX documents_number ON documents (lower(number));

-- One row per MCP tool call (user_id arrives with OAuth in stage 4).
CREATE TABLE usage_events (
    id           bigserial PRIMARY KEY,
    user_id      bigint,
    tool         text NOT NULL,
    ts           timestamptz NOT NULL DEFAULT now(),
    latency_ms   int NOT NULL,
    result_count int,
    ok           boolean NOT NULL,
    args         jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX usage_events_user_ts ON usage_events (user_id, ts);
