import hashlib

import numpy as np
import pytest

from qonunshunos.db import connect
from qonunshunos.index.writer import (
    build_sections,
    index_document,
    refresh_fts_stats,
    short_title,
)
from qonunshunos.parser.card import parse_card
from qonunshunos.parser.document import parse_document
from qonunshunos.search.hybrid import rrf, search
from qonunshunos.text.fts import terms


class FakeEmbedder:
    """Bag-of-terms hashed into 384 dims: deterministic, no model needed."""

    name = "fake"

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(384, dtype=np.float32)
        for term in terms(text):
            v[int(hashlib.md5(term.encode()).hexdigest(), 16) % 384] += 1.0
        norm = np.linalg.norm(v)
        return v / norm if norm else v + 1 / np.sqrt(384)

    def passages(self, texts):
        return np.stack([self._vec(t) for t in texts]) if texts else np.zeros((0, 384))

    def query(self, text):
        return self._vec(text)


def test_rrf_sums_reciprocal_ranks():
    scores = rrf([[1, 2, 3], [3, 1]], k=60)
    assert scores[1] == pytest.approx(1 / 61 + 1 / 62)
    assert scores[3] == pytest.approx(1 / 63 + 1 / 61)
    assert max(scores, key=scores.get) == 1


def test_build_sections_interleaves_headings(fixture_html):
    doc = parse_document(fixture_html("doc_mehnat_kodeksi.html"), -6257288)
    rows = build_sections(doc)
    kinds = [r.kind for r in rows]
    assert kinds.count("modda") == len(doc.units) - sum(u.kind != "modda" for u in doc.units)
    first_article = kinds.index("modda")
    assert {"qism", "boʻlim", "bob"} <= set(kinds[:first_article])
    bob = next(r for r in rows if r.kind == "bob")
    assert bob.elem_id is not None and bob.level == 3


def test_short_title(fixture_html):
    code = parse_document(fixture_html("doc_mehnat_kodeksi.html"), -6257288)
    assert short_title(code, None) == "Mehnat kodeksi"
    decree = parse_document(fixture_html("doc_pf60.html"), -5841063)
    card = parse_card(fixture_html("card1_in_force.html"), -5841063)
    card.form = "Указ"
    assert short_title(decree, card) == (
        "Prezident farmoni PF-60: 2022-2026-yillarga moʻljallangan Yangi Oʻzbekistonning "
        "taraqqiyot strategiyasi toʻgʻrisida"
    )


@pytest.mark.db
def test_index_and_search(db_dsn, fixture_html):
    doc = parse_document(fixture_html("doc_mehnat_kodeksi.html"), -6257288)
    card = parse_card(fixture_html("card1_in_force.html"), -6257288)
    card.status = "in_force"
    embedder = FakeEmbedder()
    with connect(db_dsn) as conn:
        count = index_document(conn, doc, card, embedder)
        assert count and count >= len(doc.units) - 5
        assert index_document(conn, doc, card, embedder) is None  # unchanged → skipped
        assert refresh_fts_stats(conn) > 100

        unit = next(u for u in doc.units if u.kind == "modda" and u.title)
        for mode in ("fts", "vector", "hybrid"):
            assert search(conn, embedder, unit.title, mode=mode, limit=5), mode
        for mode in ("fts", "hybrid"):  # the fake embedder is too crude to rank reliably
            hits = search(conn, embedder, unit.title, mode=mode, limit=5)
            assert unit.number in [h.unit_number for h in hits], mode
        top = search(conn, embedder, unit.title, limit=1)[0]
        assert top.url.startswith("https://lex.uz/docs/-6257288#")

        card.status = "lost_force"
        index_document(conn, doc, card, embedder)
        assert conn.execute("SELECT count(*) FROM chunks").fetchone()[0] == 0
        assert search(conn, embedder, unit.title) == []
