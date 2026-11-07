-- Stage 5: nightly update state and lex.uz "amendment pending" banners.

-- Banners shown above a document ("Hujjatga oʻzgartirish kiritilmoqda"). Kept out of
-- content_hash so that a banner appearing does not re-embed the whole document.
ALTER TABLE documents ADD COLUMN pending_changes jsonb NOT NULL DEFAULT '[]';

-- When each indexed document was last fetched from lex.uz, and until when it is rechecked
-- every night because a new act links to it.
CREATE TABLE crawl_state (
    doc_id        bigint PRIMARY KEY,
    checked_at    timestamptz,
    changed_at    timestamptz,
    recheck_until timestamptz,
    last_error    text
);

-- Acts seen in the lex.uz RSS feed, with the documents their text links to.
CREATE TABLE rss_seen (
    doc_id   bigint PRIMARY KEY,
    title    text NOT NULL,
    info     text,
    seen_at  timestamptz NOT NULL DEFAULT now(),
    links    bigint[] NOT NULL DEFAULT '{}',
    error    text
);

-- One row per nightly `qonunshunos update` run; the morning report reads the latest.
CREATE TABLE update_runs (
    id          bigserial PRIMARY KEY,
    started_at  timestamptz NOT NULL,
    finished_at timestamptz NOT NULL DEFAULT now(),
    report      jsonb NOT NULL
);
