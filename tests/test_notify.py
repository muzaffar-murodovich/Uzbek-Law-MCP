import json
import os
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from qonunshunos.db import connect
from qonunshunos.notify import NotifyError, morning_report, send


def test_send_posts_to_telegram():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"ok": True})

    send("123:abc", "42", "salom", transport=httpx.MockTransport(handler))
    assert seen == [
        (
            "/bot123:abc/sendMessage",
            {"chat_id": "42", "text": "salom", "disable_web_page_preview": True},
        )
    ]


def test_send_errors_do_not_leak_the_token():
    def handler(request):
        return httpx.Response(401, json={"ok": False, "description": "Unauthorized"})

    with pytest.raises(NotifyError) as err:
        send("123:secret", "42", "x", transport=httpx.MockTransport(handler))
    assert "secret" not in str(err.value) and "401" in str(err.value)
    with pytest.raises(NotifyError):
        send("", "", "x")


@pytest.mark.db
def test_morning_report(db_dsn, tmp_path):
    now = datetime(2026, 11, 8, 3, 0, tzinfo=UTC)  # 08:00 in Tashkent
    report = {
        "rss_new": [{"id": -1, "title": "Qonun", "links": [-97664]}],
        "added": [],
        "changed": [
            {"id": -97664, "title": "Maʼmuriy javobgarlik toʻgʻrisidagi kodeks", "chunks": 9}
        ],
        "lost_force": [],
        "pending": [],
        "errors": [],
        "checked": 12,
        "requests": 30,
    }
    dump = tmp_path / "qonunshunos_20261108_044000.dump"
    dump.write_bytes(b"x" * 2_000_000)
    stamp = (now - timedelta(hours=3)).timestamp()
    os.utime(dump, (stamp, stamp))
    with connect(db_dsn, vector=False) as conn:
        conn.execute(
            "INSERT INTO update_runs (started_at, finished_at, report) VALUES (%s, %s, %s)",
            (now - timedelta(hours=5), now - timedelta(hours=5), json.dumps(report)),
        )
        conn.execute("INSERT INTO users (email, last_seen_at) VALUES ('a@b', %s)", (now,))
        conn.execute(
            "INSERT INTO usage_events (tool, ts, latency_ms, ok)"
            " VALUES ('search_law', %s, 1, true), ('get_article', %s, 1, true)",
            (now - timedelta(hours=12), now - timedelta(hours=1)),  # yesterday 20:00, today
        )
        text = morning_report(conn, tmp_path, tmp_path, now=lambda: now)
    assert text.splitlines()[0] == "Qonunshunos · 08.11 hisobot"
    assert "tekshirildi 12, oʻzgardi 1" in text
    assert "~ Maʼmuriy javobgarlik toʻgʻrisidagi kodeks" in text
    assert "1 tasi bizdagi hujjatlarga havola qiladi" in text
    assert "kecha 1 qidiruv, 0 boshqa" in text
    assert "Zaxira: 3 soat oldin (2 MB)" in text
    assert "home'ga: hech qachon ⚠" in text
