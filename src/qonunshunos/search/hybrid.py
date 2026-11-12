"""Hybrid search: full-text (FTS) and vector candidates merged with Reciprocal Rank Fusion."""

import logging
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

import psycopg

from qonunshunos.index.embed import Embed
from qonunshunos.search.rerank import Rerank, blended_order
from qonunshunos.text.fts import terms

Mode = Literal["hybrid", "fts", "vector"]

_log = logging.getLogger(__name__)

CANDIDATES = 50
RRF_K = 60
EF_SEARCH = 100
SNIPPET = 400
LEX_BASE = "https://lex.uz/docs"


@dataclass
class Hit:
    document_id: int
    document: str  # short title
    number: str | None
    status: str
    last_change_date: str | None
    section_id: int
    kind: str
    unit_number: str | None
    unit_title: str | None
    path: list[str]
    url: str
    snippet: str
    score: float
    pending_changes: bool = False  # lex.uz banner: an amendment is not merged into the text yet
    ranks: dict[str, int] = field(default_factory=dict)  # best rank per list, for debugging


def rrf(rankings: Sequence[Sequence[int]], k: int = RRF_K) -> dict[int, float]:
    """``Σ 1 / (k + rank)`` over all ranked lists (rank starts at 1)."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return scores


def _filters(statuses: Sequence[str], doc_types: Sequence[str] | None) -> tuple[str, list]:
    sql = " AND d.status = ANY(%s)"
    params: list = [list(statuses)]
    if doc_types:
        sql += " AND d.doc_kind = ANY(%s)"
        params.append(list(doc_types))
    return sql, params


HEADING_BONUS = 0.5  # extra weight when a term occurs in the chunk heading
COMMON_DF = 0.05  # terms in more than 5 % of chunks only score, they do not select


TOTAL_TTL = 600.0  # seconds; the count only drifts with the nightly update
_total: tuple[float, int] | None = None


def chunk_total(conn: psycopg.Connection) -> int:
    """``count(*)`` of chunks, cached: on the full corpus it costs ~70 ms per query."""
    global _total
    now = time.monotonic()
    if _total is None or now - _total[0] > TOTAL_TTL:
        _total = (now, conn.execute("SELECT count(*) FROM chunks").fetchone()[0])
    return _total[1]


def idf_weights(
    conn: psycopg.Connection, words: Sequence[str]
) -> tuple[dict[str, float], dict[str, float]]:
    """BM25-style IDF and document share of each query term; unknown terms are dropped."""
    total = chunk_total(conn)
    rows = conn.execute(
        "SELECT word, ndoc FROM fts_stats WHERE word = ANY(%s)", (list(words),)
    ).fetchall()
    df = dict(rows)
    return {w: math.log((total - df[w] + 0.5) / (df[w] + 0.5) + 1) for w in words if df.get(w)}, {
        w: df[w] / max(total, 1) for w in words if df.get(w)
    }


def fts_candidates(
    conn: psycopg.Connection,
    query: str,
    *,
    use_stem: bool = True,
    statuses: Sequence[str] = ("in_force",),
    doc_types: Sequence[str] | None = None,
    limit: int = CANDIDATES,
) -> list[int]:
    """Chunks ranked by the summed IDF of matching query terms (+ bonus for heading matches)."""
    words = list(dict.fromkeys(terms(query, use_stem)))
    weights, share = idf_weights(conn, words)
    if not weights:
        return []
    selective = [w for w in weights if share[w] <= COMMON_DF] or list(weights)
    score_parts, params = [], []
    for word, weight in weights.items():
        score_parts.append(
            "%s * ((c.tsv @@ to_tsquery('simple', %s))::int"
            " + %s * (c.tsv @@ to_tsquery('simple', %s))::int)"
        )
        params += [weight, word, HEADING_BONUS, f"{word}:A"]
    where, filter_params = _filters(statuses, doc_types)
    rows = conn.execute(
        f"""
        SELECT c.id, {" + ".join(score_parts)} AS score
        FROM chunks c JOIN documents d ON d.id = c.document_id
        WHERE c.tsv @@ to_tsquery('simple', %s) {where}
        ORDER BY score DESC, length(c.text), c.id
        LIMIT %s
        """,
        [*params, " | ".join(selective), *filter_params, limit],
    ).fetchall()
    return [r[0] for r in rows]


def vector_candidates(
    conn: psycopg.Connection,
    embedder: Embed,
    query: str,
    *,
    statuses: Sequence[str] = ("in_force",),
    doc_types: Sequence[str] | None = None,
    limit: int = CANDIDATES,
) -> list[int]:
    vector = embedder.query(query).tolist()
    with conn.transaction():
        conn.execute(f"SET LOCAL hnsw.ef_search = {int(EF_SEARCH)}")
        if tuple(statuses) == ("in_force",) and not doc_types:
            # Only documents in force have chunks: no join, plain index scan.
            rows = conn.execute(
                "SELECT id FROM chunks WHERE embedding IS NOT NULL"
                " ORDER BY embedding <=> %s::halfvec LIMIT %s",
                [vector, limit],
            ).fetchall()
        else:
            where, params = _filters(statuses, doc_types)
            conn.execute("SET LOCAL hnsw.iterative_scan = strict_order")
            rows = conn.execute(
                f"""
                SELECT c.id
                FROM chunks c JOIN documents d ON d.id = c.document_id
                WHERE c.embedding IS NOT NULL {where}
                ORDER BY c.embedding <=> %s::halfvec
                LIMIT %s
                """,
                [*params, vector, limit],
            ).fetchall()
    return [r[0] for r in rows]


def search(
    conn: psycopg.Connection,
    embedder: Embed,
    query: str,
    alt_queries: Sequence[str] = (),
    *,
    mode: Mode = "hybrid",
    doc_types: Sequence[str] | None = None,
    statuses: Sequence[str] = ("in_force",),
    limit: int = 8,
    use_stem: bool = True,
    reranker: Rerank | None = None,
    rerank_top: int = 0,
) -> list[Hit]:
    """Best chunk per unit, ranked by RRF over FTS and vector lists of every query.

    With a ``reranker``, the first ``rerank_top`` units are reordered by the cross-encoder's
    reading of the question and each unit's best chunk, blended with the fused order.
    """
    lists: dict[str, list[int]] = {}
    for i, q in enumerate([query, *alt_queries]):
        if mode in ("hybrid", "fts"):
            lists[f"fts{i}"] = fts_candidates(
                conn, q, use_stem=use_stem, statuses=statuses, doc_types=doc_types
            )
        if mode in ("hybrid", "vector"):
            lists[f"vec{i}"] = vector_candidates(
                conn, embedder, q, statuses=statuses, doc_types=doc_types
            )
    scores = rrf(list(lists.values()))
    if not scores:
        return []
    ranks: dict[int, dict[str, int]] = {}
    for name, ranking in lists.items():
        for rank, chunk_id in enumerate(ranking, start=1):
            ranks.setdefault(chunk_id, {})[name] = rank

    rows = conn.execute(
        """
        SELECT c.id, c.section_id, c.text, d.id, d.display_title, d.number, d.status,
               d.last_change_date, s.kind, s.number, s.title, s.path, s.elem_id,
               d.pending_changes <> '[]'
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        JOIN sections s ON s.id = c.section_id
        WHERE c.id = ANY(%s)
        """,
        (list(scores),),
    ).fetchall()
    best: dict[int, Hit] = {}
    texts: dict[int, str] = {}  # section -> full text of its best chunk (what a reranker reads)
    for row in sorted(rows, key=lambda r: -scores[r[0]]):
        chunk_id, section_id, text, doc_id = row[0], row[1], row[2], row[3]
        hit = best.get(section_id)
        if hit is not None:
            hit.score += scores[chunk_id] * 0.1  # small bonus for several matching pieces
            continue
        texts[section_id] = text
        elem_id = row[12]
        best[section_id] = Hit(
            document_id=doc_id,
            document=row[4],
            number=row[5],
            status=row[6],
            last_change_date=row[7].isoformat() if row[7] else None,
            section_id=section_id,
            kind=row[8],
            unit_number=row[9],
            unit_title=row[10],
            path=list(row[11] or []),
            url=f"{LEX_BASE}/{doc_id}" + (f"#{elem_id}" if elem_id is not None else ""),
            snippet=text if len(text) <= SNIPPET else text[:SNIPPET].rsplit(" ", 1)[0] + " …",
            score=scores[chunk_id],
            pending_changes=bool(row[13]),
            ranks=ranks.get(chunk_id, {}),
        )
    hits = sorted(best.values(), key=lambda h: -h.score)
    if reranker is not None and rerank_top > 0 and len(hits) > 1:
        head = hits[: max(rerank_top, 2)]
        started = time.perf_counter()
        order = blended_order(reranker.score(query, [texts[h.section_id] for h in head]))
        head = [head[i] for i in order]
        for position, hit in enumerate(head, start=1):
            hit.ranks["rerank"] = position
        _log.debug("reranked %d units in %.2f s", len(head), time.perf_counter() - started)
        hits = head + hits[len(head) :]
    return hits[:limit]
