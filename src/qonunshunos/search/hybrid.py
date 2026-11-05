"""Hybrid search: full-text (FTS) and vector candidates merged with Reciprocal Rank Fusion."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

import psycopg

from qonunshunos.index.embed import Embed
from qonunshunos.text.fts import to_tsquery

Mode = Literal["hybrid", "fts", "vector"]

CANDIDATES = 50
RRF_K = 60
EF_SEARCH = 80
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
        sql += " AND d.doc_type = ANY(%s)"
        params.append(list(doc_types))
    return sql, params


def fts_candidates(
    conn: psycopg.Connection,
    query: str,
    *,
    use_stem: bool = True,
    statuses: Sequence[str] = ("in_force",),
    doc_types: Sequence[str] | None = None,
    limit: int = CANDIDATES,
) -> list[int]:
    tsquery = to_tsquery(query, use_stem)
    if tsquery is None:
        return []
    where, params = _filters(statuses, doc_types)
    rows = conn.execute(
        f"""
        SELECT c.id
        FROM chunks c JOIN documents d ON d.id = c.document_id,
             to_tsquery('simple', %s) q
        WHERE c.tsv @@ q {where}
        ORDER BY ts_rank_cd(c.tsv, q, 1) DESC, c.id
        LIMIT %s
        """,
        [tsquery, *params, limit],
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
    where, params = _filters(statuses, doc_types)
    with conn.transaction():
        conn.execute(f"SET LOCAL hnsw.ef_search = {int(EF_SEARCH)}")
        conn.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
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
) -> list[Hit]:
    """Best chunk per unit, ranked by RRF over FTS and vector lists of every query."""
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
        SELECT c.id, c.section_id, c.text, d.id, d.short_title, d.number, d.status,
               d.last_change_date, s.kind, s.number, s.title, s.path, s.elem_id
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        JOIN sections s ON s.id = c.section_id
        WHERE c.id = ANY(%s)
        """,
        (list(scores),),
    ).fetchall()
    best: dict[int, Hit] = {}
    for row in sorted(rows, key=lambda r: -scores[r[0]]):
        chunk_id, section_id, text, doc_id = row[0], row[1], row[2], row[3]
        hit = best.get(section_id)
        if hit is not None:
            hit.score += scores[chunk_id] * 0.1  # small bonus for several matching pieces
            continue
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
            ranks=ranks.get(chunk_id, {}),
        )
    return sorted(best.values(), key=lambda h: -h.score)[:limit]
