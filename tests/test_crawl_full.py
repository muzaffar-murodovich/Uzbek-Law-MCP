import json

import httpx

from qonunshunos.crawler.client import LexClient
from qonunshunos.crawler.full import (
    ERROR_PAUSE,
    ERRORS_PER_HOUR,
    FIRST_YEAR,
    ScopeItem,
    build_scope,
    crawl_scope,
    load_scope,
    scope_dir,
)
from qonunshunos.crawler.pipeline import Workspace

EMPTY_LISTING = "<html><body>0 hujjat topildi</body></html>"


class FakeTime:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 3))
        self.now += seconds


def make_client(handler, fake: FakeTime) -> LexClient:
    return LexClient(
        base_url="https://lex.test",
        transport=httpx.MockTransport(handler),
        sleep=fake.sleep,
        clock=fake.clock,
    )


def test_build_scope_lists_each_year_once(tmp_path, fixture_html):
    gets = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if request.method == "POST":
            return httpx.Response(200, text=fixture_html("list_codes_p2.html"))
        gets.append(dict(params))
        if (params.get("minor") == "N" and params.get("fyear") == "2026") or "minor" not in params:
            return httpx.Response(200, text=fixture_html("list_codes_p1.html"))
        return httpx.Response(200, text=EMPTY_LISTING)

    ws = Workspace(tmp_path)
    fake = FakeTime()
    report = build_scope(make_client(handler, fake), ws, last_year=2026, say=lambda s: None)
    years = 2026 - FIRST_YEAR + 1
    assert report.files == 2 * years
    assert report.listed == 28
    assert report.total == 28
    assert report.short == []
    assert all(g["status"] == "Y" and g["lang"] == "4" for g in gets)

    saved = json.loads((scope_dir(ws) / "N-2026.json").read_text())
    assert saved["expected"] == 28 and len(saved["rows"]) == 28

    gets.clear()
    again = build_scope(make_client(handler, fake), ws, last_year=2026, say=lambda s: None)
    assert again.fetched_files == 0 and again.listed == 28
    assert len(gets) == 1  # only the scope total


def _write_scope(ws: Workspace, minor: str, year: int, ids: list[int]) -> None:
    folder = scope_dir(ws)
    folder.mkdir(parents=True, exist_ok=True)
    rows = [{"lex_id": i, "title": f"Act {i}"} for i in ids]
    payload = {"minor": minor, "year": year, "expected": len(ids), "rows": rows}
    (folder / f"{minor}-{year}.json").write_text(json.dumps(payload))


def test_load_scope_orders_self_contained_acts_first_newest_first(tmp_path):
    ws = Workspace(tmp_path)
    _write_scope(ws, "Y", 2026, [-9])
    _write_scope(ws, "N", 2019, [-3, -4])
    _write_scope(ws, "N", 2025, [-1, -2])
    _write_scope(ws, "Y", 2020, [-1])  # listed twice: kept once, in its first place
    items = load_scope(ws)
    assert [i.lex_id for i in items] == [-1, -2, -3, -4, -9]
    assert items[0].minor == "N" and items[-1].minor == "Y"


def _doc_handler(fixture_html, fail: set[int] | None = None):
    fail = fail or set()

    def handler(request: httpx.Request) -> httpx.Response:
        lex_id = int(request.url.path.rsplit("/", 1)[1])
        if lex_id in fail:
            return httpx.Response(403, text="forbidden")
        if request.url.path.startswith("/actinfo/card1/"):
            return httpx.Response(200, text=fixture_html("card1_in_force.html"))
        return httpx.Response(200, text=fixture_html("doc_pf60.html"))

    return handler


def _items(ids):
    return [ScopeItem(i, "N", 2026, f"Act {i}") for i in ids]


def test_crawl_scope_skips_stored_and_waits_for_nightly_update(tmp_path, fixture_html):
    ws = Workspace(tmp_path)
    fake = FakeTime()
    client = make_client(_doc_handler(fixture_html), fake)
    pauses = iter([True, True, False])
    stats = crawl_scope(
        client, ws, _items([-1, -2]), total=2,
        paused=lambda: next(pauses, False), sleep=fake.sleep, clock=fake.clock,
        say=lambda s: None, state_file=tmp_path / "state.json",
    )  # fmt: skip
    assert stats.fetched == 2 and stats.done == 0 and not stats.failed
    assert fake.sleeps.count(60) == 2
    assert ws.parsed_path(-2).exists()
    assert json.loads((tmp_path / "state.json").read_text())["fetched"] == 2

    again = crawl_scope(
        client, ws, _items([-1, -2]), total=2,
        paused=lambda: False, sleep=fake.sleep, clock=fake.clock, say=lambda s: None,
    )  # fmt: skip
    assert again.done == 2 and again.fetched == 0


def test_crawl_scope_pauses_after_error_streak_and_stops_on_error_flood(tmp_path, fixture_html):
    ws = Workspace(tmp_path)
    fake = FakeTime()
    bad = set(range(-200, -100))
    client = make_client(_doc_handler(fixture_html, fail=bad), fake)
    messages = []
    stats = crawl_scope(
        client, ws, _items(sorted(bad, reverse=True)), total=len(bad),
        notify=messages.append, paused=lambda: False, sleep=fake.sleep, clock=fake.clock,
        say=lambda s: None,
    )  # fmt: skip
    assert ERROR_PAUSE in fake.sleeps
    assert any("ketma-ket" in m for m in messages)
    # 10 errors take ≈20 s, then a 10-minute pause: the 51st error within an hour stops the crawl.
    assert stats.stopped is not None
    assert len(stats.failed) == ERRORS_PER_HOUR + 1
