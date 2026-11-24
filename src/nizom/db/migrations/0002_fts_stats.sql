-- Document frequency of every FTS term over chunks; refreshed after (re)indexing.
-- Used for IDF weighting of query terms.
CREATE TABLE fts_stats (
    word  text PRIMARY KEY,
    ndoc  int NOT NULL
);
