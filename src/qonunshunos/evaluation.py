"""Retrieval evaluation: does the expected article show up in the top results?"""

import json
import time
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from qonunshunos.search.hybrid import Hit


@dataclass(frozen=True)
class Expected:
    document: int
    article: str  # unit number: "161", "126¹", band "5"


@dataclass
class Question:
    id: str
    question: str
    expected: list[Expected]
    tags: list[str] = field(default_factory=list)
    alt: list[str] = field(default_factory=list)


def load_questions(path: Path) -> list[Question]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    questions = []
    seen = set()
    for item in raw:
        if item["id"] in seen:
            raise ValueError(f"duplicate question id {item['id']}")
        seen.add(item["id"])
        questions.append(
            Question(
                id=str(item["id"]),
                question=item["question"],
                expected=[
                    Expected(int(e["document"]), str(e["article"])) for e in item["expected"]
                ],
                tags=list(item.get("tags", [])),
                alt=list(item.get("alt", [])),
            )
        )
    return questions


def first_rank(hits: Sequence[Hit], expected: Sequence[Expected]) -> int | None:
    wanted = {(e.document, e.article) for e in expected}
    for rank, hit in enumerate(hits, start=1):
        if (hit.document_id, hit.unit_number) in wanted:
            return rank
    return None


@dataclass
class Metrics:
    n: int
    recall_at_1: float
    recall_at_5: float
    recall_at_10: float
    mrr: float


def metrics(ranks: Sequence[int | None]) -> Metrics:
    n = len(ranks)
    if n == 0:
        return Metrics(0, 0.0, 0.0, 0.0, 0.0)

    def recall(k: int) -> float:
        return sum(1 for r in ranks if r is not None and r <= k) / n

    mrr = sum(1 / r for r in ranks if r is not None and r <= 10) / n
    return Metrics(n, recall(1), recall(5), recall(10), mrr)


SearchFn = Callable[[Question, str], list[Hit]]


def run(questions: Sequence[Question], search_fn: SearchFn, modes: Sequence[str]) -> dict:
    """Ranks per mode and question, overall and per-tag metrics."""
    report: dict = {"modes": {}, "questions": {}}
    for mode in modes:
        ranks: dict[str, int | None] = {}
        started = time.perf_counter()
        tops: dict[str, list[str]] = {}
        for q in questions:
            hits = search_fn(q, mode)
            ranks[q.id] = first_rank(hits, q.expected)
            tops[q.id] = [f"{h.document} {h.unit_number}" for h in hits[:3]]
        elapsed = (time.perf_counter() - started) / max(len(questions), 1)
        by_tag: dict[str, list[int | None]] = defaultdict(list)
        for q in questions:
            for tag in q.tags:
                by_tag[tag].append(ranks[q.id])
        report["modes"][mode] = {
            "overall": asdict(metrics(list(ranks.values()))),
            "by_tag": {t: asdict(metrics(r)) for t, r in sorted(by_tag.items())},
            "ms_per_query": round(elapsed * 1000, 1),
        }
        for q in questions:
            entry = report["questions"].setdefault(q.id, {"question": q.question, "ranks": {}})
            entry["ranks"][mode] = ranks[q.id]
            entry.setdefault("top3", {})[mode] = tops[q.id]
    return report


def format_report(report: dict) -> str:
    lines = [f"{'mode':<8} {'n':>4} {'R@1':>6} {'R@5':>6} {'R@10':>6} {'MRR':>6} {'ms':>7}"]
    for mode, data in report["modes"].items():
        m = data["overall"]
        lines.append(
            f"{mode:<8} {m['n']:>4} {m['recall_at_1']:>6.2f} {m['recall_at_5']:>6.2f} "
            f"{m['recall_at_10']:>6.2f} {m['mrr']:>6.2f} {data['ms_per_query']:>7.1f}"
        )
    last = list(report["modes"])[-1] if report["modes"] else None
    if last:
        lines.append(f"\nby tag ({last}): R@10")
        for tag, m in report["modes"][last]["by_tag"].items():
            lines.append(f"  {tag:<16} {m['n']:>4} {m['recall_at_10']:>6.2f}")
        misses = [
            (qid, q) for qid, q in report["questions"].items() if q["ranks"].get(last) is None
        ]
        lines.append(f"\nmissed in top-10 ({last}): {len(misses)}")
        for qid, q in misses:
            lines.append(f"  {qid}: {q['question']}  → {', '.join(q['top3'][last])}")
    return "\n".join(lines)


def save_report(report: dict, folder: Path, label: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{time.strftime('%Y-%m-%d')}-{label}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return path
