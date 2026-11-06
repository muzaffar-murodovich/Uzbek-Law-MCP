"""Tools against a tiny indexed corpus (needs QONUNSHUNOS_TEST_DSN)."""

import anyio
import pytest
from fakes import FakeEmbedder

from qonunshunos.db import connect
from qonunshunos.index.writer import index_document, refresh_fts_stats
from qonunshunos.mcp import tools
from qonunshunos.parser.card import CardBody, parse_card
from qonunshunos.parser.document import parse_document

pytestmark = pytest.mark.db

MK, LAW, OLD_LAW, VM, KONST = -6257288, -7389404, -999001, -7283178, -6445145


@pytest.fixture
def corpus(db_dsn, fixture_html):
    base = parse_card(fixture_html("card1_in_force.html"), 0)
    lost = parse_card(fixture_html("card1_lost_force.html"), 0)
    cabinet = [CardBody(organ="Кабинет Министров Республики Узбекистан")]
    docs = [
        ("doc_mehnat_kodeksi.html", MK, base, {"form": "Кодекс", "bodies": []}),
        ("doc_law_omonatlar.html", LAW, base, {"form": "Закон", "bodies": []}),
        ("doc_law_omonatlar.html", OLD_LAW, lost, {"form": "Закон", "bodies": []}),
        ("doc_vm897.html", VM, base, {"form": "Постановление", "bodies": cabinet}),
        ("doc_konstitutsiya.html", KONST, base, {"form": "Конституция", "bodies": []}),
    ]
    embedder = FakeEmbedder()
    with connect(db_dsn) as conn:
        for name, lex_id, card, update in docs:
            document = parse_document(fixture_html(name), lex_id)
            index_document(
                conn, document, card.model_copy(update={"lex_id": lex_id, **update}), embedder
            )
        refresh_fts_stats(conn)
        yield conn


def test_search_law(corpus):
    result = tools.search_law(corpus, FakeEmbedder(), "mehnat shartnomasini bekor qilish")
    assert result.count > 0
    assert "Mehnat kodeksi, 161-modda" in result.text
    assert "https://lex.uz/docs/-6257288#" in result.text
    assert "alt_queries" in result.text  # hint when no rephrasing was given
    only_vm = tools.search_law(corpus, FakeEmbedder(), "ijtimoiy karta", doc_types=["vm_qarori"])
    assert only_vm.count and "Mehnat kodeksi" not in only_vm.text


def test_get_article_by_name_abbreviation_and_url(corpus):
    by_name = tools.get_article(corpus, "Mehnat kodeksi", "161-modda")
    assert by_name.text.startswith("# Mehnat kodeksi, 161-modda")
    assert "Manba: lex.uz" in by_name.text
    assert tools.get_article(corpus, "MK", "161").text == by_name.text
    url = tools.get_article(corpus, "https://lex.uz/docs/-6257288#-6257549", "1")
    assert "1-modda" in url.text


def test_get_article_missing_and_ambiguous(corpus):
    missing = tools.get_article(corpus, str(MK), "999")
    assert missing.count == 0 and "get_document" in missing.text
    clauses = tools.get_article(corpus, str(VM), "1")  # "1-band" exists in several annexes
    assert clauses.count > 1 and "get_section" in clauses.text


def test_lost_force_document_has_no_text(corpus):
    result = tools.get_article(corpus, str(OLD_LAW), "1")
    assert "kuchini yoʻqotgan" in result.text and "1-modda" not in result.text
    # by number, the act in force wins
    assert tools.get_article(corpus, "OʻRQ-1031", "1").text.startswith("# Banklardagi")


def test_get_document_and_section(corpus):
    doc = tools.get_document(corpus, str(MK))
    assert "Mundarija:" in doc.text and "[#" in doc.text and "Turi: kodeks" in doc.text
    section = tools.get_section(corpus, str(MK), "1-bob")
    assert "### 1-modda" in section.text and section.count >= 1
    assert "topilmadi" in tools.get_section(corpus, str(MK), "99-bob").text


def test_find_document_and_list_codes(corpus):
    found = tools.find_document(corpus, "orq 1031")
    assert found.count == 1 and str(LAW) in found.text
    with_lost = tools.find_document(corpus, "OʻRQ-1031", include_lost_force=True)
    assert with_lost.count == 2
    by_name = tools.find_document(corpus, "banklardagi omonatlar")
    assert str(LAW) in by_name.text
    assert tools.find_document(corpus, "omonatlar", doc_type="kodeks").count == 0
    assert tools.find_document(corpus, "OʻRQ-103").count == 0  # no fuzzy match on numbers
    assert "topilmadi" in tools.get_article(corpus, "PF-60", "1").text
    codes = tools.list_codes(corpus)
    assert "Mehnat kodeksi" in codes.text and "qisqartma MK" in codes.text
    assert "Konstitutsiya" in codes.text


def test_mcp_protocol(corpus, db_dsn):
    from mcp import Client

    from qonunshunos.mcp.server import Services, create_server

    services = Services(db_dsn, None, embedder=FakeEmbedder())
    server = create_server(services)

    async def scenario():
        async with Client(server) as client:
            listed = await client.list_tools()
            names = {t.name for t in listed.tools}
            assert names == {
                "search_law",
                "get_article",
                "get_document",
                "get_section",
                "find_document",
                "list_codes",
            }
            assert all(t.annotations.read_only_hint for t in listed.tools)
            result = await client.call_tool("get_article", {"document": "MK", "article": "161"})
            assert not result.is_error
            assert "161-modda" in result.content[0].text
            prompts = await client.list_prompts()
            assert [p.name for p in prompts.prompts] == ["yuridik_savol"]

    anyio.run(scenario)
    count = corpus.execute("SELECT count(*) FROM usage_events WHERE tool = 'get_article'")
    assert count.fetchone()[0] == 1
