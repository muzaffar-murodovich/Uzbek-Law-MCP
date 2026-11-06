"""Compare embedding models on the evaluation set (dev-only, needs ``uv sync --group bench``).

Every chunk in the database is embedded with each candidate model (cached in
``data/bench/<model>.npy``); search is exact (numpy), so results are not affected by HNSW.
FTS candidates come from the database exactly as in production, and the hybrid ranking uses
the same RRF + best-chunk-per-unit logic as ``search.hybrid.search``.

    uv run --group bench python scripts/bench_embeddings.py [model ...]
"""

import argparse
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from qonunshunos.config import Settings
from qonunshunos.db import connect
from qonunshunos.evaluation import load_questions, metrics
from qonunshunos.search.hybrid import CANDIDATES, fts_candidates, rrf


@dataclass
class Candidate:
    name: str
    repo: str
    query_prompt: str | None = None  # literal prefix; None → model's own query prompt
    doc_prompt: str | None = None
    kwargs: dict = field(default_factory=dict)


E5 = {"query_prompt": "query: ", "doc_prompt": "passage: "}
CANDIDATES_ALL = [
    Candidate("e5-small", "intfloat/multilingual-e5-small", **E5),
    Candidate("uzbek-e5-small", "sukhrobnurali/uzbek-e5-small", **E5),
    Candidate("e5-base", "intfloat/multilingual-e5-base", **E5),
    Candidate("granite-97m", "ibm-granite/granite-embedding-97m-multilingual-r2"),
    Candidate("granite-311m", "ibm-granite/granite-embedding-311m-multilingual-r2"),
    Candidate(
        "harrier-270m",
        "microsoft/harrier-oss-v1-270m",
        query_prompt="Instruct: Given a legal question in Uzbek, retrieve law articles that "
        "answer it\nQuery: ",
        doc_prompt="",
    ),
    Candidate("embeddinggemma-300m", "google/embeddinggemma-300m"),
    Candidate("bge-m3", "BAAI/bge-m3", query_prompt="", doc_prompt=""),
]


def encode(model, texts, prompt, is_query, batch_size=32):
    if prompt is None:  # use the prompts configured in the model
        fn = model.encode_query if is_query else model.encode_document
        return fn(texts, batch_size=batch_size, normalize_embeddings=True)
    return model.encode(
        [prompt + t for t in texts], batch_size=batch_size, normalize_embeddings=True
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("models", nargs="*", help="default: all candidates")
    parser.add_argument("--questions", type=Path, default=Path("eval/questions.yaml"))
    parser.add_argument("--alt-file", type=Path, help="JSON {id: [queries]} replacing alt")
    parser.add_argument("--max-seq", type=int, default=512)
    args = parser.parse_args()

    from sentence_transformers import SentenceTransformer

    settings = Settings.from_env()
    questions = load_questions(args.questions, args.alt_file)
    cache = settings.data_dir / "bench"
    cache.mkdir(parents=True, exist_ok=True)

    with connect(settings.dsn) as conn:
        rows = conn.execute(
            "SELECT c.id, c.document_id, c.section_id, s.number, c.heading, c.text"
            " FROM chunks c JOIN sections s ON s.id = c.section_id ORDER BY c.id"
        ).fetchall()
        chunk_ids = np.array([r[0] for r in rows])
        unit_of = {r[0]: (r[1], r[2], r[3]) for r in rows}  # chunk → (doc, section, number)
        passages = [f"{r[4]}\n{r[5]}" for r in rows]
        query_sets = {q.id: [q.question, *q.alt] for q in questions}
        fts = {text: fts_candidates(conn, text) for texts in query_sets.values() for text in texts}

    def rank_of(question, lists):
        scores = rrf(lists)
        best: dict[int, float] = {}
        keys: dict[int, tuple] = {}
        for chunk_id, score in scores.items():
            doc, section, number = unit_of[chunk_id]
            if section not in best or score > best[section]:
                best[section] = score
                keys[section] = (doc, number)
        order = sorted(best, key=lambda s: -best[s])
        wanted = {(e.document, e.article) for e in question.expected}
        return next((i for i, s in enumerate(order, 1) if keys[s] in wanted), None)

    chosen = [c for c in CANDIDATES_ALL if not args.models or c.name in args.models]
    results = {}
    for cand in chosen:
        print(f"== {cand.name} ({cand.repo})", flush=True)
        try:
            model = SentenceTransformer(cand.repo, device="mps", **cand.kwargs)
        except OSError as exc:  # gated or missing repositories
            print(f"   skipped: {type(exc).__name__}: {str(exc)[:120]}", flush=True)
            continue
        model.max_seq_length = min(args.max_seq, model.max_seq_length or args.max_seq)
        path = cache / f"{cand.name}.npy"
        started = time.perf_counter()
        if path.exists() and np.load(path, mmap_mode="r").shape[0] == len(passages):
            doc_vecs = np.load(path).astype(np.float32)
            encode_s = None
        else:
            parts, step = [], 1024
            for start in range(0, len(passages), step):
                parts.append(
                    encode(model, passages[start : start + step], cand.doc_prompt, is_query=False)
                )
                done = min(start + step, len(passages))
                spent = time.perf_counter() - started
                eta = spent / done * (len(passages) - done)
                print(
                    f"   {done}/{len(passages)} passages, {spent / 60:.1f} min, "
                    f"~{eta / 60:.1f} min left",
                    flush=True,
                )
            doc_vecs = np.concatenate(parts)
            np.save(path, doc_vecs.astype(np.float16))
            encode_s = round(time.perf_counter() - started, 1)

        per_mode = {"vector": [], "hybrid": [], "vector+alt": [], "hybrid+alt": []}
        for q in questions:
            texts = query_sets[q.id]
            q_vecs = encode(model, texts, cand.query_prompt, is_query=True)
            vec_lists = []
            for qv in q_vecs:
                top = np.argsort(-(doc_vecs @ qv))[:CANDIDATES]
                vec_lists.append([int(chunk_ids[i]) for i in top])
            per_mode["vector"].append(rank_of(q, [vec_lists[0]]))
            per_mode["hybrid"].append(rank_of(q, [fts[texts[0]], vec_lists[0]]))
            per_mode["vector+alt"].append(rank_of(q, vec_lists))
            per_mode["hybrid+alt"].append(rank_of(q, [fts[t] for t in texts] + vec_lists))
        results[cand.name] = {
            "dim": int(doc_vecs.shape[1]),
            "encode_s": encode_s,
            **{
                mode: {"r10": round(m.recall_at_10, 3), "mrr": round(m.mrr, 3)}
                for mode, ranks in per_mode.items()
                for m in [metrics(ranks)]
            },
        }
        r = results[cand.name]
        print(
            f"   dim={r['dim']} encode={encode_s}s  vector R@10={r['vector']['r10']}"
            f"  hybrid R@10={r['hybrid']['r10']} MRR={r['hybrid']['mrr']}"
            f"  | +alt: vector {r['vector+alt']['r10']} hybrid {r['hybrid+alt']['r10']}"
            f" MRR={r['hybrid+alt']['mrr']}",
            flush=True,
        )
        del model

    label = args.questions.stem + (f"-{args.alt_file.stem}" if args.alt_file else "")
    out = Path("eval/results") / f"{time.strftime('%Y-%m-%d')}-embedding-models-{label}.json"
    previous = json.loads(out.read_text()) if out.exists() else {}
    out.write_text(json.dumps({**previous, **results}, indent=1), encoding="utf-8")
    print(f"saved {out}")


if __name__ == "__main__":
    main()
