-- e5 similarities sit in a narrow band, so the default graph (m=16, ef_construction=64)
-- missed many true neighbours. A denser graph recovers ~90 % of the exact top-50.
DROP INDEX IF EXISTS chunks_embedding;
CREATE INDEX chunks_embedding ON chunks USING hnsw (embedding halfvec_cosine_ops)
    WITH (m = 32, ef_construction = 200);
