"""Telegram messages for the operator: alerts and the morning report (docs/stage5-ops.md)."""

import shutil
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import psycopg

from qonunshunos.auth.limits import SEARCH_TOOLS, TASHKENT, day_start

API = "https://api.telegram.org"
MAX_TEXT = 4000  # Telegram allows 4096 characters per message


class NotifyError(Exception):
    pass


def send(token: str, chat_id: str, text: str, transport: httpx.BaseTransport | None = None):
    if not token or not chat_id:
        raise NotifyError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are not set")
    if len(text) > MAX_TEXT:
        text = text[: MAX_TEXT - 2] + " …"
    with httpx.Client(timeout=20, transport=transport) as client:
        response = client.post(
            f"{API}/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        )
    if response.status_code != 200:
        # The token is part of the URL: never echo the request, only Telegram's description.
        raise NotifyError(f"Telegram: {response.status_code} {response.text[:200]}")


def _ago(then: datetime | None, now: datetime) -> str:
    if then is None:
        return "hech qachon"
    hours = (now - then).total_seconds() / 3600
    return f"{hours:.0f} soat oldin" if hours < 48 else f"{hours / 24:.0f} kun oldin"


def _newest(folder: Path, pattern: str) -> Path | None:
    files = sorted(folder.glob(pattern), key=lambda p: p.stat().st_mtime) if folder.is_dir() else []
    return files[-1] if files else None


def _mtime(path: Path | None) -> datetime | None:
    return datetime.fromtimestamp(path.stat().st_mtime, UTC) if path and path.exists() else None


def morning_report(
    conn: psycopg.Connection,
    backups: Path,
    data_dir: Path,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> str:
    at = now()
    today = day_start(at)
    yesterday = today - timedelta(days=1)
    lines = [f"Qonunshunos · {at.astimezone(TASHKENT):%d.%m} hisobot"]

    run = conn.execute(
        "SELECT finished_at, report FROM update_runs ORDER BY finished_at DESC LIMIT 1"
    ).fetchone()
    if run is None:
        lines.append("Yangilash: hali ishlamagan")
    else:
        finished, report = run
        stale = " ⚠" if at - finished > timedelta(hours=30) else ""
        linking = [i for i in report["rss_new"] if i["links"]]
        lines.append(
            f"Yangilash ({_ago(finished, at)}{stale}): tekshirildi {report['checked']},"
            f" oʻzgardi {len(report['changed'])}, yangi {len(report['added'])},"
            f" xato {len(report['errors'])} · {report['requests']} soʻrov"
        )
        lines.append(
            f"RSS: {len(report['rss_new'])} yangi hujjat,"
            f" {len(linking)} tasi bizdagi hujjatlarga havola qiladi"
        )
        for name, label in (
            ("added", "+"),
            ("changed", "~"),
            ("lost_force", "✗ kuchini yoʻqotdi:"),
            ("pending", "⏳ oʻzgartirish kutilmoqda:"),
        ):
            lines += [f"  {label} {item['title']}" for item in report[name][:5]]
        lines += [f"  ! {item['id']}: {item['error'][:80]}" for item in report["errors"][:3]]

    users, active = conn.execute(
        "SELECT count(*), count(*) FILTER (WHERE last_seen_at >= %s) FROM users", (yesterday,)
    ).fetchone()
    search, other = conn.execute(
        "SELECT count(*) FILTER (WHERE tool = ANY(%(s)s)),"
        " count(*) FILTER (WHERE tool <> ALL(%(s)s))"
        " FROM usage_events WHERE ts >= %(from)s AND ts < %(to)s",
        {"s": list(SEARCH_TOOLS), "from": yesterday, "to": today},
    ).fetchone()
    lines.append(
        f"Foydalanuvchilar: {users} (kecha faol {active}) · kecha {search} qidiruv, {other} boshqa"
    )

    dump = _newest(backups, "qonunshunos_*.dump")
    size = f" ({dump.stat().st_size / 1e6:.0f} MB)" if dump else ""
    pulled = _mtime(backups / ".pulled")
    pulled_note = " ⚠" if pulled is None or at - pulled > timedelta(hours=30) else ""
    free = shutil.disk_usage(data_dir if data_dir.exists() else Path("/")).free / 1e9
    lines.append(
        f"Zaxira: {_ago(_mtime(dump), at)}{size} · home'ga: {_ago(pulled, at)}{pulled_note}"
        f" · disk: {free:.0f} GB boʻsh"
    )
    return "\n".join(lines)
