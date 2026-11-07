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
        pages = {
            "/uz/rss": self.html("rss.xml"),
            f"/docs/{AMENDING}": self.html("doc_orq1186_amending.html"),
            f"/docs/{MJTK}": self.html("doc_mjtk_pending.html"),
            f"/docs/{KONST}": self.konst,
            f"/actinfo/card1/{MJTK}": self.code_card(),
            f"/actinfo/card1/{KONST}": self.code_card(),
            f"/actinfo/card1/{VM_ABOUT_CODE}": self.new_act_card,
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
    assert report.checked == 2 and report.errors == []
    assert report.changed == [] and report.added == []  # the VM decision is not a code
    assert not ws.parsed_path(VM_ABOUT_CODE).exists()  # so `index` will not pick it up
    assert [p["id"] for p in report.pending] == [MJTK]
    stored = conn.execute("SELECT pending_changes FROM documents WHERE id = %s", (MJTK,))
    assert stored.fetchone()[0][0]["basis"][0]["doc_id"] == AMENDING
    # RSS + 4 new acts + the VM decision's card + 2 documents × (page + card)
    assert report.requests == len(lex.requests) == 10
    assert conn.execute("SELECT count(*) FROM update_runs").fetchone()[0] == 1


def test_following_nights(setup):
    conn, client, lex, ws = setup
    run_update(conn, client, ws, FakeEmbedder(), now=lambda: T0)

    # Same night again: nothing new, nothing due.
    lex.requests.clear()
    again = run_update(conn, client, ws, FakeEmbedder(), now=lambda: T0 + timedelta(hours=1))
    assert again.checked == 0 and lex.requests == ["/uz/rss"]

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
    assert lex.requests == ["/uz/rss"] and len(dry.rss_new) == 4 and dry.checked == 2
    assert conn.execute("SELECT count(*) FROM rss_seen").fetchone()[0] == 0

    small = run_update(conn, client, ws, FakeEmbedder(), budget=3, now=lambda: T0)
    assert small.requests <= 3 and small.checked == 0


def test_new_code_is_added(setup):
    conn, client, lex, ws = setup
    lex.new_act_card = lex.code_card()  # pretend the act about the Water code is a code itself
    report = run_update(conn, client, ws, FakeEmbedder(), now=lambda: T0)
    assert [a["id"] for a in report.added] == [VM_ABOUT_CODE]
    row = conn.execute("SELECT doc_kind FROM documents WHERE id = %s", (VM_ABOUT_CODE,))
    assert row.fetchone()[0] == "kodeks"
    assert lex.requests.count(f"/docs/{VM_ABOUT_CODE}") == 1
