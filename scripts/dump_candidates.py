"""Save the FTS and vector candidate lists of every evaluation question to one file.

    uv run python scripts/dump_candidates.py --questions eval/questions_llm_full.yaml \
        --alt-file eval/alt_llm_questions_llm_full.json --out data/eval/candidates_llm_full.json.gz

Fusion and ranking variants can then be tried offline (scripts/fusion_lab.py) without the
database: one run here replaces a 40-minute evaluation per variant. For each question and each
query text (the question, then its alternative queries) the file holds the ranked chunk ids of
both lists to ``--depth``, plus the unit (section) and document of every chunk.
"""

import argparse
import gzip
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from qonunshunos.config import Settings
from qonunshunos.db import connect
from qonunshunos.evaluation import Question, load_questions
from qonunshunos.index.embed import Embedder
from qonunshunos.search import hybrid


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", type=Path, default=Path("eval/questions_llm_full.yaml"))
    parser.add_argument("--alt-file", type=Path)
    parser.add_argument("--depth", type=int, default=200)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    questions = load_questions(args.questions, args.alt_file)
    settings = Settings.from_env()
    embedder = Embedder(settings.model_dir)
    ef_search = max(hybrid.EF_SEARCH, 2 * args.depth)  # HNSW returns at most ef_search rows
    hybrid.EF_SEARCH = ef_search
    local = threading.local()  # psycopg connections are not shared between threads
    opened = []

    def conn():
        if not hasattr(local, "conn"):
            local.conn = connect(settings.dsn)
            opened.append(local.conn)
        return local.conn

    def one(q: Question) -> dict:
        db = conn()
        queries = [q.question, *q.alt]
        return {
            "id": q.id,
            "tags": q.tags,
            "queries": queries,
            "expected": [[e.document, e.article, e.within] for e in q.expected],
            "fts": [hybrid.fts_candidates(db, text, limit=args.depth) for text in queries],
            "vector": [
                hybrid.vector_candidates(db, embedder, text, limit=args.depth) for text in queries
            ],
        }

    rows = []
    try:
        with ThreadPoolExecutor(args.workers) as pool:
            for done, row in enumerate(pool.map(one, questions), start=1):
                rows.append(row)
                if done % 10 == 0 or done == len(questions):
                    print(f"{done}/{len(questions)}", file=sys.stderr, flush=True)

        chunk_ids = sorted(
            {
                c
                for row in rows
                for lists in (row["fts"], row["vector"])
                for ranking in lists
                for c in ranking
            }
        )
        chunks: dict[int, int] = {}  # chunk id -> section id
        sections: dict[int, list] = {}  # section id -> [document id, kind, number, path]
        documents: dict[int, list] = {}  # document id -> [doc_kind, display_title]
        db = conn()
        for start in range(0, len(chunk_ids), 5000):
            found = db.execute(
                """
                SELECT c.id, c.section_id, d.id, s.kind, s.number, s.path, d.doc_kind,
                       d.display_title
                FROM chunks c
                JOIN sections s ON s.id = c.section_id
                JOIN documents d ON d.id = c.document_id
                WHERE c.id = ANY(%s)
                """,
                (chunk_ids[start : start + 5000],),
            ).fetchall()
            for chunk_id, section_id, doc_id, kind, number, path, doc_kind, title in found:
                chunks[chunk_id] = section_id
                sections[section_id] = [doc_id, kind, number, list(path or [])]
                documents[doc_id] = [doc_kind, title]
            print(
                f"chunk details {min(start + 5000, len(chunk_ids))}/{len(chunk_ids)}",
                file=sys.stderr,
                flush=True,
            )
    finally:
        for c in opened:
            c.close()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "settings": {
            "questions": str(args.questions),
            "alt": str(args.alt_file or "questions"),
            "depth": args.depth,
            "ef_search": ef_search,
        },
        "questions": rows,
        "chunks": chunks,
        "sections": sections,
        "documents": documents,
    }
    with gzip.open(args.out, "wt", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    size = args.out.stat().st_size / 1e6
    print(f"saved {args.out}: {len(rows)} questions, {len(chunks)} chunks, {size:.1f} MB")


if __name__ == "__main__":
    main()
