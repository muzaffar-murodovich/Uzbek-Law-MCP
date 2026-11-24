"""What stemming and the lemma table add: the production search with three FTS term forms (6n).

Runs on a copy of the server database restored from a nightly dump into a private PostgreSQL
cluster (no pgvector needed: the embedding column is restored as text and the vector search is
replaced by an exact numpy search over the same vectors). Everything else is the production code
path of ``nizom eval``: FTS with IDF, RRF, the fine-tuned reranker on the top 30.

    NIZOM_DSN=postgresql://nizom@/nizom?host=<socket dir>&port=5441 \
        uv run python scripts/fts_ablation.py lemma --out-dir <dir>

Variants (``tsv`` is rebuilt to match unless ``--no-rebuild``):
    none   words are only folded (lower case, apostrophes dropped), no stemming
    stem   the light suffix stripper as it was before the lemma table (commit d7d1c2d)
    lemma  production: lemma table + stemmer + restored vowels (commit f0160c4)

Questions: the unambiguous (``aniq``) ones of eval/questions_llm_full.yaml with the LLM's
alternative queries, as in the README numbers.
"""

import argparse
import json
import sys
import threading
import time
from pathlib import Path

import numpy as np
import yaml

from nizom.config import Settings
from nizom.db import connect
from nizom.evaluation import format_report, load_questions, run
from nizom.index.embed import Embedder
from nizom.index.writer import rebuild_fts, refresh_fts_stats
from nizom.search import hybrid
from nizom.search.rerank import Reranker
from nizom.text import fts

QUESTIONS = Path("eval/questions_llm_full.yaml")
ALT = Path("eval/alt_llm_questions_llm_full.json")
RERANK_TOP = 30

# The stemmer before commit f0160c4: no lemma table, the "i" of -chi was taken for a possessive,
# no vowel restoration.
_OLD_KEEP = frozenset({"modda", "ham", "bola", "boshqa", "yana"})


def old_stem(word: str) -> str:
    if word in _OLD_KEEP:
        return word
    for slot in fts._SLOTS:
        for suffix, min_len in slot:
            if word.endswith(suffix) and len(word) - len(suffix) >= min_len:
                word = word[: -len(suffix)]
                break
        if word in _OLD_KEEP:
            return word
    if word.endswith("lig"):
        word = word[:-1] + "k"
    return word


class ExactVectors:
    """``hybrid.vector_candidates`` as an exact cosine search over the restored vectors."""

    def __init__(self, conn, cache: Path) -> None:
        if cache.exists():
            data = np.load(cache)
            self.ids, matrix = data["ids"], data["matrix"]
        else:
            rows = conn.execute("SELECT id, embedding FROM chunks ORDER BY id").fetchall()
            self.ids = np.array([r[0] for r in rows], dtype=np.int64)
            matrix = np.vstack([np.fromstring(r[1][1:-1], sep=",", dtype=np.float32) for r in rows])
            matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
            matrix = matrix.astype(np.float16)
            np.savez(cache, ids=self.ids, matrix=matrix)
        self.blocks = [matrix[i : i + 50_000] for i in range(0, len(matrix), 50_000)]
        self.memo: dict[tuple[str, int], list[int]] = {}
        self.lock = threading.Lock()

    def __call__(self, conn, embedder, query, *, statuses=("in_force",), doc_types=None, limit):
        assert tuple(statuses) == ("in_force",) and not doc_types
        key = (query, limit)
        with self.lock:
            if key in self.memo:
                return self.memo[key]
        vector = embedder.query(query).astype(np.float32)
        vector /= np.linalg.norm(vector)
        scores = np.concatenate([b.astype(np.float32) @ vector for b in self.blocks])
        top = np.argpartition(-scores, limit)[:limit]
        top = top[np.argsort(-scores[top], kind="stable")]
        result = [int(i) for i in self.ids[top]]
        with self.lock:
            self.memo[key] = result
        return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("variant", choices=["none", "stem", "lemma"])
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--no-rebuild", action="store_true", help="tsv already has this variant")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()

    if args.variant == "stem":
        fts.term = old_stem
    use_stem = args.variant != "none"
    settings = Settings.from_env()
    conn = connect(settings.dsn, vector=False)
    if not args.no_rebuild:
        started = time.perf_counter()
        rebuild_fts(conn, use_stem=use_stem, batch=20_000, progress=lambda _m: None)
        print(f"tsv rebuilt in {time.perf_counter() - started:.0f} s", file=sys.stderr)
    stats = refresh_fts_stats(conn)
    print(f"{args.variant}: {stats} distinct FTS terms", file=sys.stderr, flush=True)

    hybrid.vector_candidates = ExactVectors(conn, args.out_dir / "vectors.npz")
    tags = {q["id"]: q["tags"] for q in yaml.safe_load(QUESTIONS.read_text())}
    questions = [q for q in load_questions(QUESTIONS, ALT) if "aniq" in tags[q.id]]
    embedder = Embedder(settings.model_dir)
    reranker = Reranker(settings.model_dir)
    local = threading.local()

    def search_fn(q, mode):
        if not hasattr(local, "conn"):
            local.conn = connect(settings.dsn, vector=False)
        reranked = mode == "hybrid+rerank"
        return hybrid.search(
            local.conn,
            embedder,
            q.question,
            q.alt,
            mode="hybrid" if reranked else mode,
            limit=10,
            use_stem=use_stem,
            reranker=reranker if reranked else None,
            rerank_top=RERANK_TOP if reranked else 0,
        )

    modes = ["fts", "hybrid", "hybrid+rerank"] + (["vector"] if args.variant == "lemma" else [])
    report = run(
        questions,
        search_fn,
        modes,
        workers=args.workers,
        progress=lambda line: print(line, file=sys.stderr, flush=True),
    )
    report["settings"] = {
        "variant": args.variant,
        "fts_terms": stats,
        "questions": f"{QUESTIONS} (aniq)",
        "alt": str(ALT),
        "rerank_top": RERANK_TOP,
        "vector": "exact cosine (numpy), not HNSW",
    }
    print(format_report(report))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"fts-ablation-{args.variant}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved {out}")


if __name__ == "__main__":
    main()
