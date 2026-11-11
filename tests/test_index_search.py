import pytest
from fakes import FakeEmbedder

from qonunshunos.db import connect
from qonunshunos.index.writer import (
    build_sections,
    index_document,
    kind_and_title,
    reembed,
    refresh_fts_stats,
)
from qonunshunos.parser.card import parse_card
from qonunshunos.parser.document import parse_document
from qonunshunos.search.hybrid import rrf, search


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


def test_kind_and_title(fixture_html):
    code = parse_document(fixture_html("doc_mehnat_kodeksi.html"), -6257288)
    assert kind_and_title(code, None) == ("kodeks", "Mehnat kodeksi")
    decree = parse_document(fixture_html("doc_pf60.html"), -5841063)
    card = parse_card(fixture_html("card1_in_force.html"), -5841063)
    card.form, card.bodies = "Указ", []
    assert kind_and_title(decree, card) == (
        "farmon",
        "2022-2026-yillarga moʻljallangan Yangi Oʻzbekistonning taraqqiyot strategiyasi "
        "toʻgʻrisidagi Prezident farmoni (PF-60)",
    )
    resolution = parse_document(fixture_html("doc_vm897.html"), -7300000)
    card.form = "Постановление"
    assert kind_and_title(resolution, card)[0] == "vm_qarori"


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


class CountingEmbedder(FakeEmbedder):
    def __init__(self):
        self.embedded = 0

    def passages(self, texts):
        self.embedded += len(texts)
        return super().passages(texts)


@pytest.mark.db
def test_reindex_reuses_vectors_and_stores_banners(db_dsn, fixture_html):
    from qonunshunos.parser.models import Link, PendingChange

    doc = parse_document(fixture_html("doc_mehnat_kodeksi.html"), -6257288)
    card = parse_card(fixture_html("card1_in_force.html"), -6257288)
    card.status = "in_force"
    embedder = CountingEmbedder()
    with connect(db_dsn) as conn:
        total = index_document(conn, doc, card, embedder)
        assert embedder.embedded == total

        # A banner alone does not rewrite the document.
        banner = PendingChange(text="Hujjatga oʻzgartirish kiritilmoqda", basis=[Link(doc_id=-1)])
        doc.pending_changes = [banner]
        assert index_document(conn, doc, card, embedder) is None
        stored = conn.execute("SELECT pending_changes FROM documents").fetchone()[0]
        assert stored[0]["basis"][0]["doc_id"] == -1

        # An amended article: only its chunks are embedded again.
        unit = next(u for u in doc.units if u.kind == "modda" and u.paragraphs)
        unit.paragraphs[0].text += " Qoʻshimcha jumla."
        embedder.embedded = 0
        assert index_document(conn, doc, card, embedder) == total
        assert 1 <= embedder.embedded <= 3
        stored = conn.execute("SELECT pending_changes FROM documents").fetchone()[0]
        assert len(stored) == 1


def test_content_hash_ignores_card_language(fixture_html):
    from qonunshunos.index.writer import content_hash

    doc = parse_document(fixture_html("doc_mehnat_kodeksi.html"), -6257288)
    card = parse_card(fixture_html("card1_in_force.html"), -6257288)
    russian = card.model_copy(
        update={"form": "Кодекс", "status_raw": "Действующий", "validity": "Бессрочный"}
    )
    latin = card.model_copy(
        update={"form": "Kodeks", "status_raw": "Amalda", "validity": "Muddatsiz"}
    )
    assert content_hash(doc, russian) == content_hash(doc, latin)
    assert content_hash(doc, card) != content_hash(
        doc, card.model_copy(update={"status": "lost_force"})
    )


@pytest.mark.db
def test_reembed_only_touches_other_models(db_dsn, fixture_html):
    doc = parse_document(fixture_html("doc_mehnat_kodeksi.html"), -6257288)
    card = parse_card(fixture_html("card1_in_force.html"), -6257288)
    card.status = "in_force"
    with connect(db_dsn) as conn:
        total = index_document(conn, doc, card, FakeEmbedder())
        before = conn.execute("SELECT id, embedding::text FROM chunks ORDER BY id").fetchall()

        newer = CountingEmbedder()
        newer.name = "fake/v2"
        assert reembed(conn, newer, batch_chunks=50, progress=lambda _: None) == total
        assert newer.embedded == total
        assert conn.execute("SELECT meta->>'embed_model' FROM documents").fetchone()[0] == "fake/v2"
        after = conn.execute("SELECT id, embedding::text FROM chunks ORDER BY id").fetchall()
        assert [r[0] for r in after] == [r[0] for r in before]  # same rows, vectors rewritten

        # A second run has nothing left to do.
        assert reembed(conn, newer, progress=lambda _: None) == 0
