"""Save the text of the candidate chunks listed by scripts/dump_candidates.py.

    uv run python scripts/dump_chunk_texts.py data/eval/candidates_llm_full.json.gz \
        --out data/eval/chunk_texts_llm_full.json.gz

Rerankers read the text, so offline reranking experiments (scripts/rerank_lab.py) need it.
Only the chunks within ``--n-fts`` / ``--n-vec`` of each list are fetched. ``--heading`` saves
"heading\ntext", the form the embedding model reads (scripts/vector_lab.py).

``--all`` saves every chunk of the corpus instead (for re-embedding it on a rented GPU):

    bash scripts/with_server_db.sh uv run python scripts/dump_chunk_texts.py --all --heading \
        --out data/embed/chunk_texts_all.json.gz
"""

import argparse
import gzip
import json
import sys
from pathlib import Path

from qonunshunos.config import Settings
from qonunshunos.db import connect

BATCH = 2000


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidates", type=Path, nargs="?")
    parser.add_argument("--all", action="store_true", help="every chunk, not only candidates")
    parser.add_argument("--n-fts", type=int, default=100)
    parser.add_argument("--n-vec", type=int, default=50)
    parser.add_argument("--heading", action="store_true", help="prepend the chunk heading")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    if args.all == bool(args.candidates):
        parser.error("give a candidates file or --all")
    texts: dict[int, str] = {}
    with connect(Settings.from_env().dsn) as conn:
        if args.all:
            ids = [r[0] for r in conn.execute("SELECT id FROM chunks ORDER BY id").fetchall()]
        else:
            with gzip.open(args.candidates, "rt", encoding="utf-8") as f:
                questions = json.load(f)["questions"]
            ids = sorted(
                {c for q in questions for ranking in q["fts"] for c in ranking[: args.n_fts]}
                | {c for q in questions for ranking in q["vector"] for c in ranking[: args.n_vec]}
            )
        for start in range(0, len(ids), BATCH):
            column = "heading || E'\\n' || text" if args.heading else "text"
            rows = conn.execute(
                f"SELECT id, {column} FROM chunks WHERE id = ANY(%s)",
                (ids[start : start + BATCH],),
            ).fetchall()
            texts.update(rows)
            print(f"{min(start + BATCH, len(ids))}/{len(ids)}", file=sys.stderr, flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.out, "wt", encoding="utf-8") as f:
        json.dump(texts, f, ensure_ascii=False)
    chars = sum(len(t) for t in texts.values())
    size = args.out.stat().st_size / 1e6
    found = f"{len(texts)} of {len(ids)} chunks"
    print(f"saved {args.out}: {found}, {chars / 1e6:.0f}M chars, {size:.1f} MB")


if __name__ == "__main__":
    main()
