"""Experiment: drop low-scoring search hits ("noise") and see what it costs in recall.

    uv run python scripts/bench_cutoff.py            # writes data/cutoff/*.json, prints tables

Search runs once per question (top 10); the cut-off rules are then applied offline.
Result (2026-11-06): no rule helps, see docs/stage2-experiments.md, 6b.
"""

import json
from pathlib import Path

from qonunshunos.config import Settings
from qonunshunos.db import connect
from qonunshunos.evaluation import first_rank, load_questions
from qonunshunos.index.embed import Embedder
from qonunshunos.search.hybrid import search

D = Path("data/cutoff")
D.mkdir(parents=True, exist_ok=True)
out = D
LIMIT = 8
s = Settings.from_env()
emb = Embedder(s.model_dir)
sets = {
    "q97_alt": ("eval/questions.yaml", "eval/alt_llm.json", True),
    "q100_alt": ("eval/questions_llm.yaml", "eval/alt_llm_questions_llm.json", True),
    "q97_raw": ("eval/questions.yaml", None, False),
}
with connect(s.dsn) as conn:
    for name, (qf, af, use_alt) in sets.items():
        rows = []
        for q in load_questions(Path(qf), Path(af) if af else None):
            hits = search(conn, emb, q.question, q.alt if use_alt else [], limit=10)
            rows.append(
                {
                    "id": q.id,
                    "rank": first_rank(hits, q.expected),
                    "hits": [
                        {"score": h.score, "lists": h.ranks, "len": len(h.snippet)} for h in hits
                    ],
                }
            )
        (out / f"{name}.json").write_text(json.dumps(rows))
        print(name, len(rows))


def rule_ratio(r):
    return lambda hits: [h for h in hits if h["score"] >= r * hits[0]["score"]] if hits else hits


def rule_single(max_rank):
    def f(hits):
        keep = [
            h
            for h in hits
            if len(h["lists"]) > 1 or min(h["lists"].values(), default=99) <= max_rank
        ]
        return keep or hits[:1]

    return f


rules = {"yo'q": lambda h: h}
rules |= {f"A {int(r * 100)}%": rule_ratio(r) for r in (0.3, 0.4, 0.5, 0.6, 0.7)}
rules |= {f"B >{k}": rule_single(k) for k in (10, 20, 30)}

for name in sets:
    rows = json.loads((D / f"{name}.json").read_text())
    print(f"\n{name}: {'qoida':<8} {'R@8':>5} {'o`rtacha natija':>15} {'yo`qotilgan':>11}")
    for label, rule in rules.items():
        found = kept_total = lost = 0
        for row in rows:
            hits = row["hits"][:LIMIT]
            kept = rule(hits)
            kept_total += len(kept)
            ok_before = row["rank"] is not None and row["rank"] <= LIMIT
            ok_after = ok_before and hits[row["rank"] - 1] in kept
            found += ok_after
            lost += ok_before and not ok_after
        n = len(rows)
        print(f"{'':>9} {label:<8} {found / n:>5.2f} {kept_total / n:>15.1f} {lost:>11}")
