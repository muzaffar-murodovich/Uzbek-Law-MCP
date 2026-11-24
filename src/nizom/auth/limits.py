"""Per-user call limits: daily quotas per tool group and a per-minute rate limit.

Daily counts come straight from ``usage_events`` (indexed on ``(user_id, ts)``), so statistics
and limits never disagree. The per-minute window lives in memory: there is one server process.
"""

import threading
import time
from collections import deque
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg

TASHKENT = ZoneInfo("Asia/Tashkent")

SEARCH_TOOLS = ("search_law",)
UNMETERED_TOOLS = ("list_codes",)  # no daily quota, but still rate-limited per minute


@dataclass(frozen=True)
class Limits:
    search: int  # search_law calls per day
    other: int  # other tool and resource calls per day
    per_minute: int  # all calls


PLANS: dict[str, Limits] = {"free": Limits(search=30, other=200, per_minute=10)}

GROUP_NAMES = {"search": "qidiruv", "other": "boshqa soʻrov"}

MINUTE_MESSAGE = (
    "Juda tez-tez soʻrov yuborilmoqda (daqiqasiga {limit} tadan koʻp). "
    "Bir daqiqa kutib, qayta urinib koʻring."
)


def limits_for(plan: str, override: dict | None = None) -> Limits:
    """Plan limits with per-user overrides on top (unknown plans fall back to ``free``)."""
    base = PLANS.get(plan, PLANS["free"])
    known = {
        k: int(v) for k, v in (override or {}).items() if k in ("search", "other", "per_minute")
    }
    return replace(base, **known)


def tool_group(tool: str) -> str | None:
    """Quota group of a tool: ``search``, ``other`` or ``None`` (no daily quota)."""
    if tool in SEARCH_TOOLS:
        return "search"
    if tool in UNMETERED_TOOLS:
        return None
    return "other"


def day_start(now: datetime) -> datetime:
    """Start of the current day in Tashkent, as an aware datetime."""
    local = now.astimezone(TASHKENT)
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def until_reset(now: datetime) -> timedelta:
    return day_start(now) + timedelta(days=1) - now.astimezone(TASHKENT)


def _humanize(delta: timedelta) -> str:
    minutes = max(1, round(delta.total_seconds() / 60))
    if minutes < 60:
        return f"≈{minutes} daqiqadan keyin"
    return f"≈{round(minutes / 60)} soatdan keyin"


def daily_message(group: str, limit: int, now: datetime) -> str:
    return (
        f"Bugungi bepul limit tugadi: kuniga {limit} ta {GROUP_NAMES[group]}. "
        "Hisoblagich Toshkent vaqti bilan 00:00 da "
        f"({_humanize(until_reset(now))}) yangilanadi. "
        "Bu orada hujjatlarni bevosita lex.uz saytida koʻrishingiz mumkin. "
        "Foydalanuvchiga shuni tushuntiring va limit tugaganini yashirmang."
    )


def tools_of(group: str) -> tuple[tuple[str, ...], bool]:
    """``(tools, negate)`` for SQL: search is a fixed list, ``other`` is everything else."""
    if group == "search":
        return SEARCH_TOOLS, False
    return SEARCH_TOOLS + UNMETERED_TOOLS, True


def count_today(conn: psycopg.Connection, user_id: int, group: str, now: datetime) -> int:
    tools, negate = tools_of(group)
    op = "<> ALL" if negate else "= ANY"
    row = conn.execute(
        f"SELECT count(*) FROM usage_events WHERE user_id = %s AND ts >= %s AND counted"
        f" AND tool {op}(%s)",
        (user_id, day_start(now), list(tools)),
    ).fetchone()
    return row[0]


class MinuteWindow:
    """Sliding 60-second window of allowed calls per user."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._calls: dict[int, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, user_id: int, limit: int) -> bool:
        """Record the call and return True if fewer than ``limit`` calls in the last minute."""
        now = self._clock()
        with self._lock:
            calls = self._calls.setdefault(user_id, deque())
            while calls and now - calls[0] >= 60:
                calls.popleft()
            if len(calls) >= limit:
                return False
            calls.append(now)
            return True


def check(
    conn: psycopg.Connection,
    user_id: int,
    tool: str,
    limits: Limits,
    window: MinuteWindow,
    now: datetime | None = None,
) -> str | None:
    """Refusal text if this call is over a limit, else ``None`` (the call may run)."""
    now = now or datetime.now(TASHKENT)
    group = tool_group(tool)
    if group is not None:
        limit = getattr(limits, group)
        if count_today(conn, user_id, group, now) >= limit:
            return daily_message(group, limit, now)
    if not window.allow(user_id, limits.per_minute):
        return MINUTE_MESSAGE.format(limit=limits.per_minute)
    return None
