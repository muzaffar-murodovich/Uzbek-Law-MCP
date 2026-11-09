"""Public pages that do not need the MCP app."""

from datetime import date

import anyio

from qonunshunos import site


def test_home_shows_coverage_and_last_update():
    stats = site.Stats(documents=10432, updated=date(2026, 11, 9))
    html = site.home("https://example.org", stats).body.decode()
    assert "10 432 ta amaldagi hujjat" in html
    assert "2026-yil 9-noyabr" in html
    assert "https://example.org/mcp" in html


def test_home_without_stats_omits_coverage():
    html = site.home("https://example.org").body.decode()
    assert "amaldagi hujjat" not in html


def test_stats_failure_does_not_break_home():
    def broken():
        raise RuntimeError("db down")

    routes = {path: handler for path, _, handler in site.routes("https://x", "", broken)}
    response = anyio.run(routes["/"], None)
    assert response.status_code == 200
