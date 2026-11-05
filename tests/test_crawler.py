from urllib.parse import parse_qs

import httpx
import pytest

from qonunshunos.crawler.client import USER_AGENT, FetchError, LexClient, NotFound
from qonunshunos.crawler.listing import NEXT_PAGE_TARGET, iter_listing, parse_listing
from qonunshunos.crawler.pipeline import Workspace, fetch, parse
from qonunshunos.crawler.store import RawStore


class FakeTime:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 3))
        self.now += seconds


def make_client(handler, fake: FakeTime | None = None) -> LexClient:
    fake = fake or FakeTime()
    return LexClient(
        base_url="https://lex.test",
        transport=httpx.MockTransport(handler),
        sleep=fake.sleep,
        clock=fake.clock,
    )


# --- client --------------------------------------------------------------------------------------


def test_client_sends_user_agent_and_waits_between_requests():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["user-agent"])
        return httpx.Response(200, text="ok")

    fake = FakeTime()
    client = make_client(handler, fake)
    client.get("/a")
    fake.now += 0.5  # half a second passes before the next call
    client.get("/b")
    assert seen == [USER_AGENT, USER_AGENT]
    assert fake.sleeps == [1.5]


def test_client_redirect_to_404_page_is_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/docs/-1":
            return httpx.Response(302, headers={"Location": "/Pages/404.aspx"})
        return httpx.Response(200, text="not found page")

    with pytest.raises(NotFound):
        make_client(handler).get("/docs/-1")


def test_client_retries_server_errors_with_backoff():
    statuses = iter([503, 500, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(next(statuses), text="body")

    fake = FakeTime()
    page = make_client(handler, fake).get("/x")
    assert page.text == "body"
    # backoff 2 s and 4 s; the 2 s spacing between requests is already covered by the backoff
    assert fake.sleeps == [2.0, 4.0]


def test_client_gives_up_after_retries():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    fake = FakeTime()
    with pytest.raises(FetchError):
        make_client(handler, fake).get("/x")
    assert fake.sleeps == [2.0, 4.0, 8.0]


# --- listing -------------------------------------------------------------------------------------


def test_parse_listing_first_page(fixture_html):
    page = parse_listing(fixture_html("list_codes_p1.html"))
    assert page.total == 28
    assert page.has_next
    assert len(page.rows) == 20
    first = page.rows[0]
    assert (first.position, first.lex_id, first.in_force) == (1, -7655343, True)
    assert first.title == "Oʻzbekiston Respublikasining Suv kodeksi"
    assert {"__VIEWSTATE", "__VIEWSTATEGENERATOR"} <= set(page.form)
    lost = [r.lex_id for r in page.rows if r.in_force is False]
    assert -1286558 in lost


def test_parse_listing_last_page(fixture_html):
    page = parse_listing(fixture_html("list_codes_p2.html"))
    assert not page.has_next
    assert [r.position for r in page.rows] == list(range(21, 29))


def test_iter_listing_follows_postback(fixture_html):
    posts = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text=fixture_html("list_codes_p1.html"))
        posts.append(parse_qs(request.content.decode()))
        return httpx.Response(200, text=fixture_html("list_codes_p2.html"))

    rows = list(iter_listing(make_client(handler), "/uz/search/nat?lang=4&fform_id=3964"))
    assert len(rows) == 28
    assert len(posts) == 1
    assert posts[0]["__EVENTTARGET"] == [NEXT_PAGE_TARGET]
    assert posts[0]["__VIEWSTATE"][0].startswith("DO7dzDCQ")
    assert sum(r.in_force for r in rows) == 20


# --- store and pipeline --------------------------------------------------------------------------


def test_store_roundtrip(tmp_path):
    store = RawStore(tmp_path)
    meta = store.save("docs", -5, "<html>ʻ</html>", "https://lex.uz/docs/-5", 200)
    assert store.has("docs", -5)
    assert store.load("docs", -5) == "<html>ʻ</html>"
    assert store.meta("docs", -5)["sha256"] == meta["sha256"]


def test_fetch_and_parse(tmp_path, fixture_html):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path.startswith("/docs/"):
            return httpx.Response(200, text=fixture_html("doc_pf60.html"))
        return httpx.Response(200, text=fixture_html("card1_in_force.html"))

    ws = Workspace(tmp_path)
    client = make_client(handler)
    fetch(client, ws, -5841063)
    fetch(client, ws, -5841063)  # already stored: no new requests
    assert requests == ["/docs/-5841063", "/actinfo/card1/-5841063"]

    document, card = parse(ws, -5841063)
    assert document.number == "PF-60"
    assert card is not None and card.status == "in_force"
    assert ws.parsed_path(-5841063).exists()
