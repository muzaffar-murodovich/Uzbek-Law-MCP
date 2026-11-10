"""Try fusion variants offline on candidate lists saved by scripts/dump_candidates.py.

    uv run python scripts/fusion_lab.py data/eval/candidates_llm_full.json.gz

``fuse`` with default parameters repeats ``qonunshunos.search.hybrid.search`` (RRF over the
chunk lists of every query, best chunk per unit). The other parameters are the variants:
list weights, candidates per list, the RRF constant, a bonus for the best single rank and
document-kind weights. Numbers are for questions with ``--tag`` (default: aniq).
"""

import argparse
import gzip
import itertools
import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from qonunshunos.evaluation import Expected, metrics


@dataclass(frozen=True)
class Params:
    n_fts: int = 50  # candidates taken from each FTS list
    n_vec: int = 50
    k: int = 60  # RRF constant
    w_fts: float = 1.0
    w_vec: float = 1.0
    w_question: float = 1.0  # weight of the lists of the user's own question (alt lists: 1)
    top_bonus: float = 0.0  # extra weight on a chunk's best single contribution
    extra_chunks: float = 0.1  # share of the score of a unit's further chunks
    kind: dict = field(default_factory=dict, hash=False, compare=False)  # doc_kind -> factor

    def label(self) -> str:
        base = Params()
        changed = [
            f"{name}={getattr(self, name)}"
            for name in self.__dataclass_fields__
            if getattr(self, name) != getattr(base, name)
        ]
        return ", ".join(changed) or "current search"


class Lab:
    def __init__(self, path: Path, tag: str) -> None:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            data = json.load(f)
        self.chunks = {int(c): s for c, s in data["chunks"].items()}
        self.sections = {int(s): v for s, v in data["sections"].items()}
        self.documents = {int(d): v for d, v in data["documents"].items()}
        self.questions = [q for q in data["questions"] if tag in q["tags"]]
        for q in self.questions:
            q["expected"] = [Expected(int(d), str(a), w) for d, a, w in q["expected"]]

    def fuse(self, q: dict, p: Params) -> list[int]:
        """Ranked unit (section) ids, as ``hybrid.search`` would return them."""
        return [section for section, _chunk in self.fuse_chunks(q, p)]

    def fuse_chunks(self, q: dict, p: Params) -> list[tuple[int, int]]:
        """Ranked (unit id, its best chunk id): the chunk is what a reranker would read."""
        total: dict[int, float] = {}
        best: dict[int, float] = {}
        for kind, depth, weight in (("fts", p.n_fts, p.w_fts), ("vector", p.n_vec, p.w_vec)):
            for i, ranking in enumerate(q[kind]):
                w = weight * (p.w_question if i == 0 else 1.0)
                for rank, chunk in enumerate(ranking[:depth], start=1):
                    part = w / (p.k + rank)
                    total[chunk] = total.get(chunk, 0.0) + part
                    best[chunk] = max(best.get(chunk, 0.0), part)
        scores = {c: s + p.top_bonus * best[c] for c, s in total.items()}
        units: dict[int, float] = {}
        shown: dict[int, int] = {}
        for chunk in sorted(scores, key=lambda c: -scores[c]):
            section = self.chunks[chunk]
            score = scores[chunk]
            if section in units:
                units[section] += score * p.extra_chunks
            else:
                units[section] = score * p.kind.get(self.documents[self.sections[section][0]][0], 1)
                shown[section] = chunk
        return [(section, shown[section]) for section in sorted(units, key=lambda s: -units[s])]

    def rank(self, q: dict, p: Params) -> int | None:
        for rank, section in enumerate(self.fuse(q, p)[:10], start=1):
            doc_id, _kind, number, path = self.sections[section]
            if any(e.matches(doc_id, number, path) for e in q["expected"]):
                return rank
        return None

    def ranks(self, p: Params, questions: list[dict] | None = None) -> list[int | None]:
        return [self.rank(q, p) for q in (questions or self.questions)]

    def row(self, p: Params) -> str:
        m = metrics(self.ranks(p))
        halves = [metrics(self.ranks(p, self.questions[i::2])).recall_at_10 for i in (0, 1)]
        return (
            f"{m.recall_at_1:>5.2f} {m.recall_at_5:>5.2f} {m.recall_at_10:>6.3f} {m.mrr:>5.2f}"
            f"  {halves[0]:.2f}/{halves[1]:.2f}  {p.label()}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidates", type=Path)
    parser.add_argument("--tag", default="aniq")
    parser.add_argument("--top", type=int, default=15, help="grid rows to print")
    args = parser.parse_args()
    lab = Lab(args.candidates, args.tag)
    header = f"{'R@1':>5} {'R@5':>5} {'R@10':>6} {'MRR':>5}  halves     variant"
    print(f"{len(lab.questions)} questions with tag {args.tag}\n{header}")
    base = Params()
    singles = [
        base,
        replace(base, w_vec=0.0),
        replace(base, w_fts=0.0),
        replace(base, w_vec=0.5),
        replace(base, w_vec=0.25),
        replace(base, w_question=0.5),
        replace(base, w_question=0.0),
        replace(base, k=10),
        replace(base, k=20),
        replace(base, top_bonus=1.0),
        replace(base, top_bonus=3.0),
        replace(base, n_fts=100),
        replace(base, n_fts=200, n_vec=200),
        replace(base, extra_chunks=0.0),
        replace(base, extra_chunks=0.3),
    ]
    for p in singles:
        print(lab.row(p))

    print(f"\ngrid, best {args.top} by R@10 then MRR\n{header}")
    grid = [
        Params(n_fts=n, k=k, w_vec=wv, w_question=wq, top_bonus=tb)
        for n, k, wv, wq, tb in itertools.product(
            (50, 100), (10, 20, 60), (0.0, 0.25, 0.5, 1.0), (0.5, 1.0), (0.0, 1.0, 3.0)
        )
    ]
    scored = []
    for p in grid:
        m = metrics(lab.ranks(p))
        scored.append((m.recall_at_10, m.mrr, p))
    for _r10, _mrr, p in sorted(scored, key=lambda t: (-t[0], -t[1]))[: args.top]:
        print(lab.row(p))


if __name__ == "__main__":
    main()
