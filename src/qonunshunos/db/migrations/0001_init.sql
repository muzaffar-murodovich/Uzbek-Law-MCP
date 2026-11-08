CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- One row per lex.uz document (Latin version, negative lex id).
-- Documents that lost force, or have no HTML text yet, keep only their requisites.
CREATE TABLE documents (
    id               bigint PRIMARY KEY,
    title            text NOT NULL,
    short_title      text NOT NULL,          -- "Mehnat kodeksi" (used in chunk headings)
    doc_type         text,                   -- card1 form: "Кодекс", "Закон", "Указ", ...
    number           text,
    adopted_at       date,
    status           text NOT NULL,          -- in_force | lost_force | not_in_force | ...
    accepting_body   text,
    url              text NOT NULL,
    content          text NOT NULL,          -- html | pdf_only | requisites
    edition_date     date,
    last_change_date date,
    content_hash     text NOT NULL,
    card             jsonb,
    meta             jsonb NOT NULL DEFAULT '{}',
    title_norm       text NOT NULL,          -- folded title + number, for trigram lookup
    indexed_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX documents_title_trgm ON documents USING gin (title_norm gin_trgm_ops);
CREATE INDEX documents_type_status ON documents (doc_type, status);

-- Headings and units of a document in reading order.
CREATE TABLE sections (
    id           bigserial PRIMARY KEY,
    document_id  bigint NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    ord          int NOT NULL,
    kind         text NOT NULL,              -- qism, boʻlim, bob, ..., modda, band, kirish, matn
    level        int,                        -- headings only
    number       text,
    title        text,
    path         text[] NOT NULL DEFAULT '{}',
    elem_id      bigint,
    text         text NOT NULL DEFAULT '',
    extra        jsonb NOT NULL DEFAULT '{}', -- okoz, changes, comments, tables
    UNIQUE (document_id, ord)
);
CREATE INDEX sections_lookup ON sections (document_id, kind, number);

-- Searchable pieces of units.
CREATE TABLE chunks (
    id           bigserial PRIMARY KEY,
    document_id  bigint NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    section_id   bigint NOT NULL REFERENCES sections (id) ON DELETE CASCADE,
    ord          int NOT NULL,
    heading      text NOT NULL,
    text         text NOT NULL,
    tsv          tsvector NOT NULL,
    embedding    halfvec(384)
);
CREATE INDEX chunks_document ON chunks (document_id);
CREATE INDEX chunks_section ON chunks (section_id);
CREATE INDEX chunks_tsv ON chunks USING gin (tsv);
CREATE INDEX chunks_embedding ON chunks USING hnsw (embedding halfvec_cosine_ops)
    WITH (m = 16, ef_construction = 64);
