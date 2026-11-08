"""Nightly update against a fake lex.uz (needs QONUNSHUNOS_TEST_DSN)."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fakes import FakeEmbedder

from qonunshunos.crawler.client import LexClient
from qonunshunos.crawler.pipeline import Workspace
from qonunshunos.crawler.update import linked_ids, run_update
from qonunshunos.db import connect
from qonunshunos.index.writer import index_document
from qonunshunos.parser.card import parse_card
from qonunshunos.parser.document import parse_document

pytestmark = pytest.mark.db

MJTK, KONST, AMENDING, VM_ABOUT_CODE = -97664, -6445145, -8569963, -8551484
T0 = datetime(2026, 11, 7, 22, 30, tzinfo=UTC)


def listing(rows: list[tuple[int, str]]) -> str:
    items = "".join(
        f'<tr class="dd-table__main-item"><td class="dd-table__main-item_number">{n}</td>'
        f'<td><div class="dd-table__main-left-desc"><a href="/docs/{lex_id}">{title}</a></div>'
        '<span class="lx_act_state"><i class="status_code_y"></i></span></td></tr>'
        for n, (lex_id, title) in enumerate(rows, start=1)
    )
    return f"<html><body>{len(rows)} hujjat topildi<table>{items}</table></body></html>"


# The newest acts in scope: the VM decision is self-contained, the law only amends others.
SCOPE_N = [(VM_ABOUT_CODE, "Suv kodeksi bilan bogʻliq qaror"), (MJTK, "Maʼmuriy kodeks")]
SCOPE_Y = [(AMENDING, "Maʼmuriy kodeksga oʻzgartish kiritish toʻgʻrisida")]


class FakeLex:
    def __init__(self, fixture_html):
        self.html = fixture_html
        self.requests: list[str] = []
        self.konst = fixture_html("doc_konstitutsiya.html")
        self.new_act_card = fixture_html("card1_in_force.html")

    def code_card(self) -> str:
        return self.html("card1_in_force.html").replace("Постановление", "Кодекс")

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.requests.append(path)
        if path == "/uz/search/nat":
            minor = request.url.params.get("minor")
            return httpx.Response(200, text=listing(SCOPE_N if minor == "N" else SCOPE_Y))
        pages = {
            "/uz/rss": self.html("rss.xml"),
            f"/docs/{AMENDING}": self.html("doc_orq1186_amending.html"),
            f"/docs/{MJTK}": self.html("doc_mjtk_pending.html"),
            f"/docs/{KONST}": self.konst,
            f"/actinfo/card1/{MJTK}": self.code_card(),
            f"/actinfo/card1/{KONST}": self.code_card(),
            f"/actinfo/card1/{VM_ABOUT_CODE}": self.new_act_card,
            f"/actinfo/card1/{AMENDING}": self.html("card1_in_force.html"),
        }
        if path in pages:
            return httpx.Response(200, text=pages[path])
        if path.startswith("/docs/"):
            return httpx.Response(200, text=self.html("doc_pf60.html"))
        return httpx.Response(404, text="")


@pytest.fixture
def setup(db_dsn, fixture_html, tmp_path):
    lex = FakeLex(fixture_html)
    client = LexClient(
        base_url="https://lex.test",
        transport=httpx.MockTransport(lex),
        sleep=lambda s: None,
        min_interval=0,
    )
    with connect(db_dsn) as conn:
        for name, lex_id in (("doc_mjtk_pending.html", MJTK), ("doc_konstitutsiya.html", KONST)):
            url = f"https://lex.test/docs/{lex_id}"
            document = parse_document(fixture_html(name), lex_id, url=url)
            document.pending_changes = []  # stored before lex.uz put up the banner
            index_document(conn, document, parse_card(lex.code_card(), lex_id), FakeEmbedder())
        yield conn, client, lex, Workspace(tmp_path)


def test_linked_ids(fixture_html):
    document = parse_document(fixture_html("doc_orq1186_amending.html"), AMENDING)
    assert linked_ids(document) == {MJTK, -111460}


def test_first_night(setup):
    conn, client, lex, ws = setup
    report = run_update(conn, client, ws, FakeEmbedder(), now=lambda: T0)

    assert report.rss_items == 4
    links = {i["id"]: i["links"] for i in report.rss_new}
    assert links[AMENDING] == [MJTK]
    assert report.checked == 4 and report.errors == []
    assert report.changed == []
    assert [a["id"] for a in report.added] == [VM_ABOUT_CODE, AMENDING]
    assert [p["id"] for p in report.pending] == [MJTK]
    stored = conn.execute("SELECT pending_changes FROM documents WHERE id = %s", (MJTK,))
    assert stored.fetchone()[0][0]["basis"][0]["doc_id"] == AMENDING
    # RSS + 4 new acts + 2 listings + 2 cards of listed acts + 2 documents × (page + card)
    assert report.requests == len(lex.requests) == 13
    assert conn.execute("SELECT count(*) FROM update_runs").fetchone()[0] == 1


def test_following_nights(setup):
    conn, client, lex, ws = setup
    run_update(conn, client, ws, FakeEmbedder(), now=lambda: T0)

    # Same night again: nothing new, nothing due.
    lex.requests.clear()
    again = run_update(conn, client, ws, FakeEmbedder(), now=lambda: T0 + timedelta(hours=1))
    assert again.checked == 0 and again.added == []
    assert lex.requests == ["/uz/rss", "/uz/search/nat", "/uz/search/nat"]

    # Next night: the code linked by the new act is checked again, the Constitution is not.
    lex.requests.clear()
    next_night = run_update(conn, client, ws, FakeEmbedder(), now=lambda: T0 + timedelta(days=1))
    assert next_night.checked == 1
    assert f"/docs/{MJTK}" in lex.requests and f"/docs/{KONST}" not in lex.requests

    # A week later the Constitution has changed on lex.uz.
    lex.konst = lex.konst.replace("suvereniteti", "davlat suvereniteti", 1)
    week = run_update(conn, client, ws, FakeEmbedder(), now=lambda: T0 + timedelta(days=8))
    assert [c["id"] for c in week.changed] == [KONST]


def test_budget_and_dry_run(setup):
    conn, client, lex, ws = setup
    dry = run_update(conn, client, ws, FakeEmbedder(), dry_run=True, now=lambda: T0)
    assert lex.requests == ["/uz/rss", "/uz/search/nat", "/uz/search/nat"]
    assert len(dry.rss_new) == 4 and len(dry.added) == 2 and dry.checked == 2
    assert conn.execute("SELECT count(*) FROM rss_seen").fetchone()[0] == 0

    small = run_update(conn, client, ws, FakeEmbedder(), budget=3, now=lambda: T0)
    assert small.requests <= 3 and small.checked == 0


def test_listed_acts_are_added_amending_ones_by_requisites(setup):
    conn, client, lex, ws = setup
    lex.new_act_card = lex.code_card()  # pretend the act about the Water code is a code itself
    run_update(conn, client, ws, FakeEmbedder(), now=lambda: T0)
    rows = dict(conn.execute("SELECT id, doc_kind FROM documents").fetchall())
    assert rows[VM_ABOUT_CODE] == "kodeks"
    content = dict(conn.execute("SELECT id, content FROM documents").fetchall())
    assert content[VM_ABOUT_CODE] == "html" and content[AMENDING] == "requisites"
    chunks = conn.execute("SELECT count(*) FROM chunks WHERE document_id = %s", (AMENDING,))
    assert chunks.fetchone()[0] == 0
    assert lex.requests.count(f"/docs/{VM_ABOUT_CODE}") == 1  # stored when read from RSS
