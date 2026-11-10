"""Try rerankers offline on the candidates saved by dump_candidates.py and dump_chunk_texts.py.

    uv run --group bench python scripts/rerank_lab.py score --model BAAI/bge-reranker-v2-m3
    uv run --group bench python scripts/rerank_lab.py report

``score`` takes the first ``--top`` units of the fused list of every question, lets a
cross-encoder score (query, chunk text) pairs and caches the scores in ``data/eval/rerank/``.
``report`` reorders the first N units by those scores and prints recall next to the fused
baseline. Scores are computed per query text: the question (q) and its alternatives (a1, a2).
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fusion_lab import Lab, Params

from qonunshunos.evaluation import metrics

FUSION = Params(n_fts=100, k=20, w_vec=0.5)  # best fusion variant; its pool is what we rerank
CACHE = Path("data/eval/rerank")
VARIANTS = ("q", "a1", "a2")


def cache_path(model: str, variant: str) -> Path:
    return CACHE / f"{model.replace('/', '__')}.{variant}.json"


def load_texts(path: Path) -> dict[int, str]:
    import gzip

    with gzip.open(path, "rt", encoding="utf-8") as f:
        return {int(k): v for k, v in json.load(f).items()}


def score(args: argparse.Namespace) -> None:
    import torch
    from sentence_transformers import CrossEncoder

    lab = Lab(args.candidates, args.tag)
    texts = load_texts(args.texts)
    model = CrossEncoder(args.model, max_length=args.max_length, trust_remote_code=True)
    questions = lab.questions[: args.limit] if args.limit else lab.questions
    for index, variant in enumerate(VARIANTS):
        if variant not in args.variants.split(","):
            continue
        path = cache_path(args.model, variant)
        done = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        pairs = []
        for q in questions:
            if index >= len(q["queries"]):
                continue
            for _section, chunk in lab.fuse_chunks(q, FUSION)[: args.top]:
                key = f"{q['id']}:{chunk}"
                if key not in done:
                    pairs.append((key, q["queries"][index], texts[chunk]))
        pairs.sort(key=lambda t: len(t[2]))  # similar lengths in a batch: less padding
        started = time.perf_counter()
        for start in range(0, len(pairs), args.batch * 20):
            block = pairs[start : start + args.batch * 20]
            with torch.inference_mode():
                values = model.predict(
                    [(query, text) for _key, query, text in block], batch_size=args.batch
                )
            done.update({key: float(v) for (key, _q, _t), v in zip(block, values, strict=True)})
            CACHE.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(done), encoding="utf-8")
            rate = (start + len(block)) / (time.perf_counter() - started)
            print(
                f"{variant}: {start + len(block)}/{len(pairs)} pairs, {rate:.1f} pairs/s",
                file=sys.stderr,
                flush=True,
            )
        if pairs:
            rate = len(pairs) / (time.perf_counter() - started)
            meta = CACHE / f"{args.model.replace('/', '__')}.speed.json"
            meta.write_text(json.dumps({"pairs_per_s": rate, "threads": torch.get_num_threads()}))


def report(args: argparse.Namespace) -> None:
    lab = Lab(args.candidates, args.tag)
    models = sorted({p.name.rsplit(".", 2)[0] for p in CACHE.glob("*.q.json")})
    header = f"{'R@1':>5} {'R@5':>5} {'R@10':>6} {'MRR':>5}  halves     variant"
    print(f"{len(lab.questions)} questions with tag {args.tag}\n{header}")

    def line(name: str, ranks: list[int | None]) -> str:
        m = metrics(ranks)
        halves = [metrics(ranks[i::2]).recall_at_10 for i in (0, 1)]
        return (
            f"{m.recall_at_1:>5.2f} {m.recall_at_5:>5.2f} {m.recall_at_10:>6.3f} {m.mrr:>5.2f}"
            f"  {halves[0]:.2f}/{halves[1]:.2f}  {name}"
        )

    def first(q: dict, order: list[int]) -> int | None:
        for rank, section in enumerate(order[:10], start=1):
            doc_id, _kind, number, path = lab.sections[section]
            if any(e.matches(doc_id, number, path) for e in q["expected"]):
                return rank
        return None

    pools = {q["id"]: lab.fuse_chunks(q, FUSION) for q in lab.questions}
    print(
        line(
            "fused, no reranker", [first(q, [s for s, _ in pools[q["id"]]]) for q in lab.questions]
        )
    )
    for model in models:
        scores = {}
        for variant in VARIANTS:
            path = CACHE / f"{model}.{variant}.json"
            if path.exists():
                scores[variant] = json.loads(path.read_text(encoding="utf-8"))
        speed_file = CACHE / f"{model}.speed.json"
        speed = json.loads(speed_file.read_text())["pairs_per_s"] if speed_file.exists() else 0
        print(f"\n{model}" + (f"  ({speed:.1f} pairs/s here)" if speed else ""))
        combos = [("q",), ("a1",), ("q", "a1", "a2")]
        for combo in combos:
            if any(v not in scores for v in combo):
                continue
            for top in args.tops:
                for blend in (0.0, args.blend):
                    ranks = []
                    covered = True
                    for q in lab.questions:
                        pool = pools[q["id"]][:top]
                        values = []
                        for position, (_section, chunk) in enumerate(pool, start=1):
                            found = [scores[v].get(f"{q['id']}:{chunk}") for v in combo]
                            if any(x is None for x in found):
                                covered = False
                                break
                            values.append((max(found), position))
                        if not covered:
                            break
                        # blend: reciprocal-rank mix of the reranker order and the fused order
                        by_score = sorted(range(len(pool)), key=lambda i: -values[i][0])
                        rerank_pos = {i: r for r, i in enumerate(by_score, start=1)}
                        order = sorted(
                            range(len(pool)),
                            key=lambda i: -(1 / (10 + rerank_pos[i]) + blend / (10 + values[i][1])),
                        )
                        ranks.append(first(q, [pool[i][0] for i in order]))
                    if not covered:
                        continue
                    name = f"top {top:>3}, query {'+'.join(combo)}" + (
                        f", blend {blend}" if blend else ""
                    )
                    seconds = f"  ~{top * len(combo) / speed:.1f} s/question" if speed else ""
                    print(line(name + seconds, ranks))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("score", "report"):
        p = sub.add_parser(name)
        p.add_argument(
            "--candidates", type=Path, default=Path("data/eval/candidates_llm_full.json.gz")
        )
        p.add_argument("--tag", default="aniq")
    p = sub.choices["score"]
    p.add_argument("--texts", type=Path, default=Path("data/eval/chunk_texts_llm_full.json.gz"))
    p.add_argument("--model", required=True)
    p.add_argument("--top", type=int, default=100, help="fused units scored per question")
    p.add_argument("--variants", default="q,a1,a2")
    p.add_argument("--max-length", type=int, default=512)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--limit", type=int, default=0, help="only the first N questions (smoke test)")
    p = sub.choices["report"]
    p.add_argument("--tops", type=int, nargs="+", default=[30, 50, 100])
    p.add_argument("--blend", type=float, default=0.5)
    args = parser.parse_args()
    {"score": score, "report": report}[args.command](args)


if __name__ == "__main__":
    main()
