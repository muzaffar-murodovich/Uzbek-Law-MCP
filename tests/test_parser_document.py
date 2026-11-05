import pytest

from qonunshunos.parser.common import parse_link, uz_date_to_iso
from qonunshunos.parser.document import ParseError, classify_heading, parse_document


def units_by_number(doc, kind):
    return {u.number: u for u in doc.units if u.kind == kind}


@pytest.fixture
def mehnat(fixture_html):
    return parse_document(fixture_html("doc_mehnat_kodeksi.html"), -6257288)


@pytest.fixture
def konstitutsiya(fixture_html):
    return parse_document(fixture_html("doc_konstitutsiya.html"), -6445145)


@pytest.fixture
def pf60(fixture_html):
    return parse_document(fixture_html("doc_pf60.html"), -5841063)


@pytest.fixture
def vm897(fixture_html):
    return parse_document(fixture_html("doc_vm897.html"), -7283178)


# --- helpers -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("UMUMIY QISM", (1, "qism", "UMUMIY", "UMUMIY QISM")),
        ("I BOʻLIM. UMUMIY QOIDALAR", (2, "boʻlim", "I", "UMUMIY QOIDALAR")),
        ("BIRINCHI BOʻLIM. ASOSIY PRINSIPLAR", (2, "boʻlim", "BIRINCHI", "ASOSIY PRINSIPLAR")),
        ("1-bob. Asosiy qoidalar", (3, "bob", "1", "Asosiy qoidalar")),
        ("I bob. Davlat suvereniteti", (3, "bob", "I", "Davlat suvereniteti")),
        (
            "5-§. Mehnat shartnomasini bekor qilish",
            (4, "paragraf", "5", "Mehnat shartnomasini bekor qilish"),
        ),
        ("MUQADDIMA", (5, "sarlavha", None, "MUQADDIMA")),
    ],
)
def test_classify_heading(text, expected):
    assert classify_heading(text) == expected


@pytest.mark.parametrize(
    ("html", "number", "title"),
    [
        ("599- modda. Lizing", "599", "Lizing"),
        ("184<sup>3</sup> -modda. Milliy", "184³", "Milliy"),
        ("126<sup>1</sup>-modda.", "126¹", None),
    ],
)
def test_article_heading_variants(html, number, title):
    block = f'<div class="CLAUSE_DEFAULT lx_elem"><div id="-2">{html}</div></div>'
    page = f'<title>x</title><div id="divCont">{block}</div>'
    doc = parse_document(page, -1)
    assert (doc.units[0].number, doc.units[0].title) == (number, title)
    assert doc.warnings == []


def test_empty_article_heading_and_table_std_are_handled():
    page = (
        '<title>x</title><div id="divCont">'
        '<div class="CLAUSE_DEFAULT lx_elem"><div id="-2"> </div></div>'
        '<div class="CLAUSE_DEFAULT lx_elem"><div id="-3">1-modda. A</div></div>'
        '<div class="TABLE_STD lx_elem"><div id="-4">'
        "<table><tr><td>a</td><td>b</td></tr></table></div></div>"
        "</div>"
    )
    doc = parse_document(page, -1)
    assert len(doc.units) == 1
    assert doc.units[0].tables[0].rows == [["a", "b"]]
    assert doc.warnings == []


def test_parse_link():
    link = parse_link("/docs/-7108715?ONDATE=21.09.2024 00#-7108833", " Qonuni ")
    assert (link.doc_id, link.elem_id, link.ondate, link.text) == (
        -7108715,
        -7108833,
        "2024-09-21",
        "Qonuni",
    )
    assert parse_link("/uz/docs/-112314").doc_id == -112314
    assert parse_link("https://example.com/docs/1") is None


def test_uz_date_to_iso():
    assert uz_date_to_iso("2022-yil 28-yanvar,") == "2022-01-28"
    assert uz_date_to_iso("Toshkent sh.") is None


# --- Mehnat kodeksi (articles) -------------------------------------------------------------------


def test_mehnat_metadata(mehnat):
    assert mehnat.content == "html"
    assert mehnat.title == "Oʻzbekiston Respublikasining Mehnat kodeksi"
    assert mehnat.date == "2022-10-28"
    assert mehnat.number is None  # the <title> of this page has no number
    assert mehnat.alternates == {"ru": 6257291, "uz-Cyrl": 6257288}
    assert mehnat.okoz[0].startswith("05.00.00.00 Mehnat")
    assert mehnat.tsz == ["Ijtimoiy-madaniy masalalar / Mehnat. Aholining bandligi"]
    assert mehnat.publication_origin.startswith("(Qonunchilik maʼlumotlari milliy bazasi")
    assert mehnat.last_change_date == "2026-10-15"
    assert mehnat.warnings == []


def test_mehnat_articles_and_paths(mehnat):
    articles = units_by_number(mehnat, "modda")
    assert {"1", "2", "3", "4", "5", "6", "160", "161"} <= set(articles)
    first = articles["1"]
    assert first.title == "Ushbu Kodeks bilan tartibga solinadigan munosabatlar"
    assert first.elem_id == -6257549
    assert first.path == ["UMUMIY QISM", "I BOʻLIM. UMUMIY QOIDALAR", "1-bob. Asosiy qoidalar"]
    assert articles["161"].path[:3] == [
        "MAXSUS QISM",
        "IV BOʻLIM. YAKKA TARTIBDAGI MEHNATGA OID MUNOSABATLAR",
        "12-bob. Mehnat shartnomasi",
    ]


def test_mehnat_article_161_content(mehnat):
    article = units_by_number(mehnat, "modda")["161"]
    texts = [p.text for p in article.paragraphs]
    assert any(t.startswith("5¹) bolani tarbiyalash") for t in texts)
    assert not any("Ҳужжатга таклиф" in t for t in texts)  # interface buttons are dropped
    assert article.okoz and article.okoz[0].startswith("05.00.00.00")

    change = next(c for c in article.changes if c.text.startswith("(161-moddaning ikkinchi qismi"))
    assert change.links[0].doc_id == -8537661
    assert change.links[0].ondate == "2026-10-15"

    assert article.comments[0].text.startswith("Qarang: mazkur Kodeksning")
    assert article.comments[0].links[0].elem_id == -6264926


def test_mehnat_interface_buttons_are_dropped(mehnat):
    texts = [u.title or "" for u in mehnat.units]
    texts += [p.text for u in mehnat.units for p in u.paragraphs]
    assert not any("Ҳужжатга таклиф" in t or "Аудиони тинглаш" in t for t in texts)


def test_mehnat_previous_edition_comments_are_dropped(mehnat):
    for unit in mehnat.units:
        assert not any(c.text.startswith("Oldingi") for c in unit.comments)


# --- Konstitutsiya -------------------------------------------------------------------------------


def test_konstitutsiya(konstitutsiya):
    doc = konstitutsiya
    assert doc.title == "Oʻzbekiston Respublikasi Konstitutsiyasi"
    assert doc.edition_date == "2026-07-25"
    assert doc.alternates["en"] == 6451070
    assert doc.notes[0].startswith("Mazkur yangi tahrirdagi")

    preamble = doc.units[0]
    assert preamble.kind == "matn"
    assert preamble.path == ["MUQADDIMA"]
    assert preamble.paragraphs[0].text == "Biz, Oʻzbekistonning yagona xalqi,"

    articles = units_by_number(doc, "modda")
    assert articles["1"].title is None
    assert articles["1"].path == [
        "BIRINCHI BOʻLIM. ASOSIY PRINSIPLAR",
        "I bob. Davlat suvereniteti",
    ]
    assert "155" in articles


# --- PF-60 (decree without articles) -------------------------------------------------------------


def test_pf60_bands_and_signature(pf60):
    doc = pf60
    assert (doc.number, doc.date) == ("PF-60", "2022-01-28")
    assert doc.accepting_body == "Oʻzbekiston Respublikasi Prezidentining"
    assert doc.units[0].kind == "kirish"
    bands = units_by_number(doc, "band")
    assert "2" in bands and "1" not in bands  # item 1 lost force
    assert bands["2"].paragraphs[0].text.startswith("2. Taraqqiyot strategiyasida")
    assert any(p.text.startswith("a) 2026-yilga qadar") for p in bands["2"].paragraphs)
    assert bands["2"].okoz[0].startswith("06.00.00.00")  # index placed before the item text

    assert doc.signature == "Oʻzbekiston Respublikasi Prezidenti Sh. MIRZIYOYEV"
    assert (doc.signed_place, doc.signed_date, doc.signed_number) == (
        "Toshkent sh.",
        "2022-01-28",
        "PF-60",
    )
    # Appendices 1–4 lost force: only their change notes remain, after the signature.
    assert [c.text[:8] for c in doc.changes] == ["(1-ilova", "(2-ilova", "(3-ilova", "(4-ilova"]


# --- VM 897 (resolution with appendices) --------------------------------------------------------


def test_vm897_appendices(vm897):
    doc = vm897
    ilovalar = [h.text for h in doc.headings if h.kind == "ilova"]
    assert ilovalar[0].startswith("1-ilova. Ijtimoiy karta bepul")
    assert ilovalar[0].endswith("ROʻYXATI")
    assert ilovalar[3] == "4-ilova. Oʻzbekiston Respublikasining ijtimoiy kartasi toʻgʻrisida NIZOM"
    assert ilovalar[4].startswith("Nizomga 1-ilova.")

    nizom_band_1 = next(
        u
        for u in doc.units
        if u.kind == "band" and u.number == "1" and u.path and "NIZOM" in u.path[0]
    )
    assert nizom_band_1.path[1] == "1-bob. Umumiy qoidalar"
    assert nizom_band_1.paragraphs[0].text.startswith("1. Ushbu Nizom")


def test_vm897_tables(vm897):
    first_appendix = next(u for u in vm897.units if u.path and u.path[0].startswith("1-ilova"))
    assert first_appendix.kind == "matn"
    # The list of 1-ilova sits in a table inside a BY_DEFAULT block.
    rows = first_appendix.tables[0].rows
    assert rows[0][0].startswith("1.")
    third = next(u for u in vm897.units if u.path and u.path[0].startswith("3-ilova"))
    assert third.tables[0].rows[0][:2] == ["T/r", "Imtiyoz va ijtimoiy kafolat nomi"]


# --- PDF-only and broken pages -------------------------------------------------------------------


def test_pdf_only(fixture_html):
    doc = parse_document(fixture_html("doc_pdf_only.html"), -8571898)
    assert doc.content == "pdf_only"
    assert doc.number == "PQ-392"
    assert doc.date == "2026-11-04"
    assert doc.title.startswith("Sogʻliqni saqlash tizimini")
    assert doc.units == []


def test_page_without_text_raises():
    with pytest.raises(ParseError):
        parse_document("<html><title>x</title></html>", -1)


def test_law_parliament_stamp_and_quoted_article(fixture_html):
    doc = parse_document(fixture_html("doc_law_omonatlar.html"), -7389404)
    assert doc.warnings == []
    assert doc.notes == [
        "Qonunchilik palatasi tomonidan 2024-yil 18-oktabrda qabul qilingan "
        "Senat tomonidan 2025-yil 24-yanvarda maʼqullangan"
    ]
    last = doc.units[-1]
    assert last.number == "47"
    # an article quoted inside an amending provision stays text of article 47
    assert any(p.text.startswith("“67²-modda.") for p in last.paragraphs)
    assert "67²" not in [u.number for u in doc.units]
