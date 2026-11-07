"""Nightly update: find new and amended acts on lex.uz and re-index them.

lex.uz has no "changed documents" list. An amendment is a separate act whose text links to the
acts it changes; lex.uz merges it into their current edition later, sometimes months later, and
meanwhile shows a banner "Hujjatga oʻzgartirish kiritilmoqda" (see docs/stage5-ops.md). So:

1. New acts from the RSS feed are fetched once; documents of ours they link to are rechecked
   every night for ``RECHECK_DAYS``. A new act in scope is added to the index.
2. Documents with a banner are rechecked every ``PENDING_EVERY`` until it disappears.
3. The rest are rechecked in turn, oldest check first and at most weekly, while the request
   budget lasts.
"""

import logging
import re
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta

import psycopg
from psycopg.types.json import Jsonb

from qonunshunos.crawler.client import LexClient, NotFound, document_path
from qonunshunos.crawler.pipeline import Workspace, fetch, parse
from qonunshunos.crawler.rss import RSS_PATH, RssItem, parse_rss
from qonunshunos.index.embed import Embed
from qonunshunos.index.writer import index_document, kind_and_title, refresh_fts_stats
from qonunshunos.parser.document import parse_document
from qonunshunos.parser.models import Link, ParsedDocument

log = logging.getLogger(__name__)

RECHECK_DAYS = 7
PENDING_EVERY = timedelta(days=2)
ROTATE_AFTER = timedelta(days=7)  # an ordinary document is fetched at most once a week
DEFAULT_BUDGET = 400  # requests per night: ≈15 minutes at one request per 2 seconds
# Titles of acts that change other acts. Their links are rechecked for a week; links from other
# acts (a district decision citing the Civil code) only once, the next night.
_AMENDS_RE = re.compile(
    r"oʻzgartirish|qoʻshimcha(lar)? kiritish|kuchini yoʻqotgan|munosabati bilan|tahrirda",
    re.IGNORECASE,
)
SCOPE_KINDS = frozenset({"konstitutsiya", "kodeks"})  # new acts added to the index


@dataclass
class Report:
    rss_items: int = 0
    rss_new: list[dict] = field(default_factory=list)  # {id, title, links: [our ids]}
    added: list[dict] = field(default_factory=list)  # {id, title}
    checked: int = 0
    changed: list[dict] = field(default_factory=list)  # {id, title, chunks}
    lost_force: list[dict] = field(default_factory=list)
    pending: list[dict] = field(default_factory=list)  # banners that appeared: {id, title, text}
    errors: list[dict] = field(default_factory=list)  # {id, error}
    requests: int = 0
    budget_left: int = 0

    def summary(self) -> str:
        linking = [i for i in self.rss_new if i["links"]]
        return (
            f"RSS: {len(self.rss_new)} yangi ({len(linking)} tasi bizdagi hujjatga havola qiladi)"
            f" · tekshirildi {self.checked}, oʻzgardi {len(self.changed)},"
            f" yangi {len(self.added)}, kuchini yoʻqotdi {len(self.lost_force)},"
            f" xato {len(self.errors)} · {self.requests} soʻrov"
        )


def linked_ids(document: ParsedDocument) -> set[int]:
    """Every document the text links to (articles, changes and comments)."""
    links: list[Link] = []
    for holder in (document, *document.units):
        for change in holder.changes:
            links += change.links
        for comment in holder.comments:
            links += comment.links
    for unit in document.units:
        for paragraph in unit.paragraphs:
            links += paragraph.links
    return {link.doc_id for link in links} - {document.lex_id}


def known_ids(conn: psycopg.Connection) -> dict[int, int]:
    """Our document ids and their other language versions → our id."""
    result: dict[int, int] = {}
    for doc_id, alternates in conn.execute(
        "SELECT id, meta->'alternates' FROM documents"
    ).fetchall():
        for other in (alternates or {}).values():
            result[int(other)] = doc_id
        result[doc_id] = doc_id
    return result


class Budget:
    def __init__(self, requests: int) -> None:
        self.left = requests
        self.used = 0

    def take(self, n: int) -> bool:
        if self.left < n:
            return False
        self.left -= n
        self.used += n
        return True


def _queue(conn: psycopg.Connection, now: datetime) -> Iterator[tuple[int, str]]:
    """Documents to recheck, most urgent first: linked by a new act, banner, oldest check."""
    rows = conn.execute(
        """
        SELECT d.id, d.display_title
        FROM documents d LEFT JOIN crawl_state s ON s.doc_id = d.id
        WHERE s.checked_at IS NULL
            OR (s.recheck_until > %(now)s AND s.checked_at < %(now)s - interval '20 hours')
            OR (d.pending_changes <> '[]' AND s.checked_at < %(now)s - %(pending)s)
            OR s.checked_at < %(now)s - %(rotate)s
        ORDER BY
            (s.recheck_until > %(now)s) IS TRUE DESC,
            (d.pending_changes <> '[]' AND (s.checked_at IS NULL
                OR s.checked_at < %(now)s - %(pending)s)) DESC,
            s.checked_at NULLS FIRST, d.id
        """,
        {"now": now, "pending": PENDING_EVERY, "rotate": ROTATE_AFTER},
    ).fetchall()
    yield from rows


def _mark(conn: psycopg.Connection, doc_id: int, now: datetime, changed: bool, error: str | None):
    conn.execute(
        """
        INSERT INTO crawl_state (doc_id, checked_at, changed_at, last_error)
        VALUES (%(id)s, %(now)s, CASE WHEN %(changed)s THEN %(now)s END, %(error)s)
        ON CONFLICT (doc_id) DO UPDATE SET checked_at = %(now)s, last_error = %(error)s,
            changed_at = CASE WHEN %(changed)s THEN %(now)s ELSE crawl_state.changed_at END
        """,
        {"id": doc_id, "now": now, "changed": changed, "error": error},
    )


def _read_rss(
    conn: psycopg.Connection,
    client: LexClient,
    ws: Workspace,
    items: list[RssItem],
    budget: Budget,
    report: Report,
    now: datetime,
    dry_run: bool,
) -> list[int]:
    """Fetch acts not seen before; returns new acts that may belong to the index."""
    seen = {r[0] for r in conn.execute("SELECT doc_id FROM rss_seen").fetchall()}
    ours = known_ids(conn)
    candidates = []
    for item in items:
        if item.lex_id in seen or item.lex_id in ours:
            continue
        if dry_run:
            report.rss_new.append({"id": item.lex_id, "title": item.title, "links": []})
            continue
        if not budget.take(1):
            break
        try:
            page = client.get(document_path(item.lex_id))
            ws.raw.save("docs", item.lex_id, page.text, page.url, page.status)
            document = parse_document(page.text, item.lex_id, url=page.url)
        except Exception as exc:  # a broken act must not stop the night; retried tomorrow
            log.warning("rss %s: %s", item.lex_id, exc)
            report.errors.append({"id": item.lex_id, "error": f"{type(exc).__name__}: {exc}"})
            continue
        targets = sorted({ours[i] for i in linked_ids(document) if i in ours})
        conn.execute(
            "INSERT INTO rss_seen (doc_id, title, info, seen_at, links) VALUES (%s, %s, %s, %s, %s)"
            " ON CONFLICT (doc_id) DO NOTHING",
            (item.lex_id, item.title, item.info, now, targets),
        )
        days = RECHECK_DAYS if _AMENDS_RE.search(item.title) else 1
        for target in targets:
            conn.execute(
                """
                INSERT INTO crawl_state (doc_id, recheck_until) VALUES (%(id)s, %(until)s)
                ON CONFLICT (doc_id) DO UPDATE SET recheck_until = GREATEST(
                    crawl_state.recheck_until, %(until)s)
                """,
                {"id": target, "until": now + timedelta(days=days)},
            )
        report.rss_new.append({"id": item.lex_id, "title": item.title, "links": targets})
        if item.lex_id < 0 and "kodeks" in f"{item.title} {item.info}".lower():
            candidates.append(item.lex_id)
    return candidates


def _check(
    conn: psycopg.Connection,
    client: LexClient,
    ws: Workspace,
    embedder: Embed,
    doc_id: int,
    report: Report,
    now: datetime,
    *,
    new: bool = False,
) -> None:
    before = conn.execute(
        "SELECT status, pending_changes FROM documents WHERE id = %s", (doc_id,)
    ).fetchone()
    try:
        fetch(client, ws, doc_id, force=not new)  # a new act's page was saved by _read_rss
        document, card = parse(ws, doc_id)
        kind, title = kind_and_title(document, card)
        if new and kind not in SCOPE_KINDS:
            return
        chunks = index_document(conn, document, card, embedder)
    except NotFound:
        report.errors.append({"id": doc_id, "error": "lex.uz: sahifa topilmadi"})
        _mark(conn, doc_id, now, False, "not found")
        return
    except Exception as exc:  # keep going; the document is retried in its next turn
        log.exception("check %s", doc_id)
        report.errors.append({"id": doc_id, "error": f"{type(exc).__name__}: {exc}"})
        _mark(conn, doc_id, now, False, f"{type(exc).__name__}: {exc}"[:500])
        return
    report.checked += 1
    entry = {"id": doc_id, "title": title}
    if new:
        report.added.append(entry)
    elif chunks is not None:
        report.changed.append({**entry, "chunks": chunks})
    status = card.status if card else "unknown"
    if before and before[0] == "in_force" and status != "in_force":
        report.lost_force.append(entry)
    if document.pending_changes and not (before and before[1]):
        report.pending.append({**entry, "text": document.pending_changes[0].text})
    _mark(conn, doc_id, now, chunks is not None, None)


def run_update(
    conn: psycopg.Connection,
    client: LexClient,
    ws: Workspace,
    embedder: Embed,
    *,
    budget: int = DEFAULT_BUDGET,
    dry_run: bool = False,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> Report:
    started = now()
    report = Report()
    left = Budget(budget)
    left.take(1)
    items = parse_rss(client.get(RSS_PATH).text)
    report.rss_items = len(items)
    candidates = _read_rss(conn, client, ws, items, left, report, started, dry_run)

    if dry_run:
        report.checked = sum(1 for _ in _queue(conn, started))
    else:
        for doc_id in candidates:
            if left.take(1):  # the card; the page is already stored
                _check(conn, client, ws, embedder, doc_id, report, now(), new=True)
        for doc_id, _title in _queue(conn, started):
            if not left.take(2):
                break
            _check(conn, client, ws, embedder, doc_id, report, now())
        if report.changed or report.added or report.lost_force:
            refresh_fts_stats(conn)
    report.requests, report.budget_left = left.used, left.left
    if not dry_run:
        conn.execute(
            "INSERT INTO update_runs (started_at, report) VALUES (%s, %s)",
            (started, Jsonb(asdict(report))),
        )
    return report
