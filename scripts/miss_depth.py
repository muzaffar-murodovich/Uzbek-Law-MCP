"""How deep is the expected article for the questions hybrid search missed?

    uv run python scripts/miss_depth.py --result eval/results/<date>-<label>.json \
        --questions eval/questions_llm_full.yaml --alt-file eval/alt_llm_questions_llm_full.json

For every question whose hybrid rank is empty in ``--result`` it reports the best rank of an
expected article in the FTS and vector candidate lists (to ``--depth``, over the question and
its alternative queries) and its rank in the fused list search builds today. The answer picks
the fix: in the pool but low means reranking, absent from deep lists means retrieval.
"""

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from qonunshunos.config import Settings
from qonunshunos.db import connect
from qonunshunos.evaluation import Question, first_rank, load_questions
from qonunshunos.index.embed import Embedder
from qonunshunos.search import hybrid

BUCKETS = [(10, "1-10"), (50, "11-50"), (200, "51-200")]


def bucket(rank: int | None) -> str:
    if rank is None:
        return "none"
    return next((name for top, name in BUCKETS if rank <= top), "200+")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--questions", type=Path, default=Path("eval/questions_llm_full.yaml"))
    parser.add_argument("--alt-file", type=Path)
    parser.add_argument("--tag", default="aniq", help="only questions with this tag")
    parser.add_argument("--depth", type=int, default=200)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    ranks = json.loads(args.result.read_text(encoding="utf-8"))["questions"]
    questions = [
        q
        for q in load_questions(args.questions, args.alt_file)
        if args.tag in q.tags and ranks[q.id]["ranks"]["hybrid"] is None
    ]
    settings = Settings.from_env()
    embedder = Embedder(settings.model_dir)
    hybrid.EF_SEARCH = max(hybrid.EF_SEARCH, 2 * args.depth)  # HNSW returns at most ef_search rows
    local = threading.local()  # psycopg connections are not shared between threads
    opened = []

    def list_rank(conn, q: Question, chunk_ids: list[int]) -> int | None:
        """Rank of the first chunk that belongs to an expected article."""
        if not chunk_ids:
            return None
        rows = conn.execute(
            """
            SELECT c.id, c.document_id, s.number, s.path
            FROM chunks c JOIN sections s ON s.id = c.section_id
            WHERE c.id = ANY(%s)
            """,
            (chunk_ids,),
        ).fetchall()
        unit = {row[0]: row[1:] for row in rows}
        for rank, chunk_id in enumerate(chunk_ids, start=1):
            doc_id, number, path = unit[chunk_id]
            if any(e.matches(doc_id, number, list(path or [])) for e in q.expected):
                return rank
        return None

    def one(q: Question) -> dict:
        if not hasattr(local, "conn"):
            local.conn = connect(settings.dsn)
            opened.append(local.conn)
        conn = local.conn
        fts, vec = [], []
        for text in [q.question, *q.alt]:
            fts.append(list_rank(conn, q, hybrid.fts_candidates(conn, text, limit=args.depth)))
            vec.append(
                list_rank(conn, q, hybrid.vector_candidates(conn, embedder, text, limit=args.depth))
            )
        fused = hybrid.search(conn, embedder, q.question, q.alt, limit=10_000)
        best = lambda xs: min((x for x in xs if x is not None), default=None)  # noqa: E731
        return {
            "id": q.id,
            "question": q.question,
            "fts": fts,
            "vector": vec,
            "best_fts": best(fts),
            "best_vector": best(vec),
            "fused": first_rank(fused, q.expected),  # today's pool: 50 candidates per list
            "pool_units": len(fused),
        }

    rows = []
    try:
        with ThreadPoolExecutor(args.workers) as pool:
            for done, row in enumerate(pool.map(one, questions), start=1):
                rows.append(row)
                if done % 10 == 0 or done == len(questions):
                    print(f"{done}/{len(questions)}", file=sys.stderr, flush=True)
    finally:
        for conn in opened:
            conn.close()

    print(f"missed questions: {len(rows)} (tag {args.tag}, depth {args.depth})")
    names = [name for _, name in BUCKETS] + ["none"]
    print(f"{'best rank':<34}" + "".join(f"{n:>8}" for n in names))
    for key, label in [
        ("best_fts", "FTS list (any query)"),
        ("best_vector", "vector list (any query)"),
        ("fused", "fused list today (50 per list)"),
    ]:
        counts = {n: 0 for n in [*names, "200+"]}
        for row in rows:
            counts[bucket(row[key])] += 1
        counts["51-200"] += counts.pop("200+")  # the fused list can be longer than --depth
        print(f"{label:<34}" + "".join(f"{counts[n]:>8}" for n in names))
    either = sum(1 for r in rows if r["best_fts"] is not None or r["best_vector"] is not None)
    print(f"in the FTS or vector list to depth {args.depth}: {either}/{len(rows)}")
    print(f"in today's fused pool at any rank: {sum(r['fused'] is not None for r in rows)}")
    if args.out:
        args.out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"saved {args.out}")


if __name__ == "__main__":
    main()
