from datetime import UTC, datetime, timedelta

import pytest

from qonunshunos.auth import limits, users
from qonunshunos.auth.limits import TASHKENT, Limits, MinuteWindow
from qonunshunos.db import connect


def test_limits_for_plan_and_override():
    assert limits.limits_for("free") == Limits(search=30, other=200, per_minute=10)
    assert limits.limits_for("free", {"search": 100}) == Limits(100, 200, 10)
    assert limits.limits_for("no-such-plan", {"bogus": 1}) == limits.PLANS["free"]


def test_tool_groups():
    assert limits.tool_group("search_law") == "search"
    assert limits.tool_group("get_article") == "other"
    assert limits.tool_group("resource_article") == "other"
    assert limits.tool_group("list_codes") is None


def test_day_starts_at_tashkent_midnight():
    # 18:59 UTC is 23:59 in Tashkent (UTC+5), 19:01 UTC is already the next day.
    before = datetime(2026, 11, 6, 18, 59, tzinfo=UTC)
    after = datetime(2026, 11, 6, 19, 1, tzinfo=UTC)
    assert limits.day_start(before) == datetime(2026, 11, 6, tzinfo=TASHKENT)
    assert limits.day_start(after) == datetime(2026, 11, 7, tzinfo=TASHKENT)
    assert limits.until_reset(before) == timedelta(minutes=1)


def test_daily_message_says_when_it_resets():
    now = datetime(2026, 11, 6, 19, 0, tzinfo=TASHKENT)
    text = limits.daily_message("search", 30, now)
    assert "kuniga 30 ta qidiruv" in text
    assert "≈5 soatdan keyin" in text
    late = datetime(2026, 11, 6, 23, 20, tzinfo=TASHKENT)
    assert "≈40 daqiqadan keyin" in limits.daily_message("other", 200, late)


def test_minute_window_slides():
    clock = [0.0]
    window = MinuteWindow(clock=lambda: clock[0])
    assert all(window.allow(1, 3) for _ in range(3))
    assert not window.allow(1, 3)
    assert window.allow(2, 3)  # other users are independent
    clock[0] = 59.9
    assert not window.allow(1, 3)
    clock[0] = 60.0
    assert window.allow(1, 3)


@pytest.fixture
def conn(db_dsn):
    with connect(db_dsn) as conn:
        yield conn


def _log(conn, user_id, tool, ts, counted=True):
    conn.execute(
        "INSERT INTO usage_events (user_id, tool, ts, latency_ms, ok, counted)"
        " VALUES (%s, %s, %s, 1, true, %s)",
        (user_id, tool, ts, counted),
    )


@pytest.mark.db
def test_sign_in_creates_once_and_refreshes_profile(conn):
    a = users.sign_in(conn, "google", "sub-1", email="a@example.com", name="Ali")
    b = users.sign_in(conn, "google", "sub-1", email="ali@example.com", name=None)
    assert a.id == b.id
    assert b.email == "ali@example.com" and b.display_name == "Ali"
    assert b.last_seen_at is not None and b.limits == limits.PLANS["free"]
    other = users.sign_in(conn, "google", "sub-2", email="v@example.com", name="Vali")
    assert other.id != a.id
    assert users.find(conn, "ALI@example.com").id == a.id
    assert users.find(conn, str(other.id)).id == other.id


@pytest.mark.db
def test_set_limits_merges_and_removes(conn):
    user = users.sign_in(conn, "dev", "x")
    user = users.set_limits(conn, user.id, {"search": 2, "other": 5})
    assert user.limits == Limits(2, 5, 10)
    user = users.set_limits(conn, user.id, {"other": None})
    assert user.limits_override == {"search": 2}


@pytest.mark.db
def test_check_counts_only_today_and_counted_calls(conn):
    user = users.sign_in(conn, "dev", "y")
    now = datetime(2026, 11, 6, 12, 0, tzinfo=TASHKENT)
    _log(conn, user.id, "search_law", now - timedelta(hours=1))
    _log(conn, user.id, "search_law", now - timedelta(days=1))  # yesterday
    _log(conn, user.id, "search_law", now - timedelta(minutes=5), counted=False)
    _log(conn, user.id, "get_article", now - timedelta(minutes=5))
    _log(conn, user.id, "list_codes", now - timedelta(minutes=5))
    assert limits.count_today(conn, user.id, "search", now) == 1
    assert limits.count_today(conn, user.id, "other", now) == 1

    tight = Limits(search=1, other=2, per_minute=10)
    window = MinuteWindow()
    refusal = limits.check(conn, user.id, "search_law", tight, window, now)
    assert refusal and "kuniga 1 ta qidiruv" in refusal
    assert limits.check(conn, user.id, "get_article", tight, window, now) is None
    assert limits.check(conn, user.id, "list_codes", tight, window, now) is None


@pytest.mark.db
def test_block_revokes_tokens(conn):
    user = users.sign_in(conn, "dev", "z")
    conn.execute(
        "INSERT INTO oauth_clients (client_id, info) VALUES ('c1', '{}');"
        "INSERT INTO oauth_tokens (token_hash, kind, client_id, user_id, scopes, expires_at)"
        f" VALUES ('h', 'access', 'c1', {user.id}, '{{qonunshunos}}', now() + interval '1 hour')"
    )
    users.block(conn, user.id, "spam")
    assert users.get(conn, user.id).blocked
    revoked = conn.execute("SELECT revoked_at FROM oauth_tokens WHERE token_hash = 'h'").fetchone()
    assert revoked[0] is not None
    users.unblock(conn, user.id)
    assert not users.get(conn, user.id).blocked
    rows = users.overview(conn, datetime.now(TASHKENT) - timedelta(days=1))
    assert [r[0].id for r in rows] == [user.id] and rows[0][1] == "dev"
