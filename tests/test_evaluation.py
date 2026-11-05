import pytest

from qonunshunos.evaluation import Expected, Question, first_rank, load_questions, metrics, run
from qonunshunos.search.hybrid import Hit


def _hit(doc: int, number: str) -> Hit:
    return Hit(doc, "D", None, "in_force", None, 0, "modda", number, None, [], "", "", 0.0)


def test_first_rank_and_metrics():
    hits = [_hit(-1, "5"), _hit(-2, "7"), _hit(-1, "9")]
    assert first_rank(hits, [Expected(-1, "9"), Expected(-3, "1")]) == 3
    assert first_rank(hits, [Expected(-2, "5")]) is None
    m = metrics([1, 3, None, 12])
    assert (m.recall_at_1, m.recall_at_5, m.recall_at_10) == (0.25, 0.5, 0.5)
    assert m.mrr == pytest.approx((1 + 1 / 3) / 4)


def test_run_reports_per_mode():
    q = Question("q1", "savol", [Expected(-1, "9")], tags=["mehnat"])
    report = run([q], lambda q, mode: [_hit(-1, "9")] if mode == "fts" else [], ["fts", "vector"])
    assert report["modes"]["fts"]["overall"]["recall_at_1"] == 1.0
    assert report["modes"]["vector"]["overall"]["recall_at_10"] == 0.0
    assert report["questions"]["q1"]["ranks"] == {"fts": 1, "vector": None}


def test_load_questions(tmp_path):
    path = tmp_path / "q.yaml"
    path.write_text(
        "- id: a\n  question: Savol?\n  expected: [{document: -6257288, article: 161}]\n"
        "  tags: [mehnat]\n",
        encoding="utf-8",
    )
    (q,) = load_questions(path)
    assert q.expected == [Expected(-6257288, "161")]
