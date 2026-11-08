"""Full crawl of the MVP scope (docs/stage6-full-crawl.md).

The scope is lex.uz's national legislation search (``/uz/search/nat``): Constitution, codes,
laws, presidential and government acts, ministry orders; local, international and court acts
live in other sections. Two steps:

1. ``build_scope``: listings of Latin acts in force, one file per (minor, year). ``minor=N`` are
   self-contained acts, ``minor=Y`` acts that only amend others. A long listing is a chain of
   ASP.NET postbacks; splitting it by year keeps chains short, and a finished year is not
   fetched again after a restart.
2. ``crawl_scope``: fetch and parse every listed act, self-contained acts first, newest first.
   Stored pages are skipped, so a restart continues where it stopped. It pauses while the
   nightly update runs (same IP), backs off on errors and stops if lex.uz keeps failing.
"""

import json
import logging
import re
import subprocess
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from qonunshunos.crawler.client import FetchError, LexClient, NotFound
from qonunshunos.crawler.listing import read_listing
from qonunshunos.crawler.pipeline import Workspace, fetch, parse

log = logging.getLogger(__name__)

NAT_LISTING = "/uz/search/nat?lang=4&status=Y"
FIRST_YEAR = 1920  # 16 acts in force are older than 1990 (oldest: 1961)
MINOR_ORDER = ("N", "Y")  # self-contained acts first, then amending acts

PAUSE_UNITS = ("qonunshunos-update.service",)  # same IP: never crawl while these run
ERROR_PAUSE = 600.0  # seconds to wait after ``ERROR_STREAK`` failures in a row
ERROR_STREAK = 10
ERRORS_PER_HOUR = 50  # more than this and the crawl stops
PROGRESS_EVERY = 6 * 3600.0


def scope_dir(ws: Workspace) -> Path:
    return ws.data_dir / "listings" / "scope"


def listing_path(minor: str, year: int) -> str:
    return f"{NAT_LISTING}&minor={minor}&fyear={year}"


@dataclass
class ScopeReport:
    total: int | None  # lex.uz's own count for the whole scope
    listed: int = 0
    files: int = 0
    fetched_files: int = 0
    short: list[str] = field(default_factory=list)  # files with fewer rows than lex.uz reported


def build_scope(
    client: LexClient,
    ws: Workspace,
    last_year: int | None = None,
    say: Callable[[str], None] = print,
) -> ScopeReport:
    folder = scope_dir(ws)
    folder.mkdir(parents=True, exist_ok=True)
    _, total = read_listing(client, NAT_LISTING, max_pages=1)
    report = ScopeReport(total=total)
    last_year = last_year or date.today().year
    for minor in MINOR_ORDER:
        for year in range(last_year, FIRST_YEAR - 1, -1):
            target = folder / f"{minor}-{year}.json"
            if target.exists():
                rows = json.loads(target.read_text(encoding="utf-8"))["rows"]
            else:
                found, expected = read_listing(client, listing_path(minor, year))
                rows = [asdict(r) for r in found]
                payload = {"minor": minor, "year": year, "expected": expected, "rows": rows}
                tmp = target.with_suffix(".tmp")
                tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
                tmp.replace(target)  # a file exists only once its listing is complete
                report.fetched_files += 1
                if expected is not None and len(rows) < expected:
                    report.short.append(target.name)
                say(f"{minor} {year}: {len(rows)} rows (lex.uz: {expected})")
            report.files += 1
            report.listed += len(rows)
    return report


@dataclass
class ScopeItem:
    lex_id: int
    minor: str
    year: int
    title: str


def load_scope(ws: Workspace) -> list[ScopeItem]:
    """Every listed act once, in crawl order: self-contained first, newest year first."""
    items, seen = [], set()
    files = []
    for path in scope_dir(ws).glob("*.json"):
        minor, year = path.stem.split("-")
        files.append((MINOR_ORDER.index(minor), -int(year), path))
    for _, _, path in sorted(files):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload["rows"]:
            if row["lex_id"] in seen:
                continue
            seen.add(row["lex_id"])
            items.append(ScopeItem(row["lex_id"], payload["minor"], payload["year"], row["title"]))
    return items


# Titles of acts that only amend others ("... oʻzgartish va qoʻshimchalar kiritish toʻgʻrisida").
# 5 357 of the 5 406 minor=Y acts match; the rest (codes approved by a decree, rules of their
# own) are indexed in full.
AMENDING_TITLE_RE = re.compile(
    r"oʻzgarti?r?ish|qoʻshimcha|kuchini yoʻqotgan|reyestridan chiqarish|munosabati bilan",
    re.IGNORECASE,
)


def requisites_only_ids(ws: Workspace) -> set[int]:
    """Amending acts (minor=Y with an amending title) whose text is not indexed."""
    return {
        item.lex_id
        for item in load_scope(ws)
        if item.minor == "Y" and AMENDING_TITLE_RE.search(item.title)
    }


RUNNING_STATES = frozenset({"active", "activating", "reloading", "deactivating"})


def unit_active(
    unit: str, run: Callable[..., subprocess.CompletedProcess] = subprocess.run
) -> bool:
    """True while the unit runs. A oneshot service (the nightly update) stays "activating" for
    its whole run, so ``systemctl is-active``'s exit code alone would miss it."""
    try:
        result = run(
            ["systemctl", "show", "-p", "ActiveState", "--value", unit],
            check=False, capture_output=True, text=True, timeout=10,
        )  # fmt: skip
    except (OSError, subprocess.TimeoutExpired):
        return False  # no systemd here (a laptop): nothing to wait for
    return result.stdout.strip() in RUNNING_STATES


@dataclass
class CrawlStats:
    total: int
    done: int = 0  # already stored before this run
    fetched: int = 0
    failed: list[dict] = field(default_factory=list)  # {id, error}
    not_found: list[int] = field(default_factory=list)
    warnings: int = 0
    stopped: str | None = None
    started: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))

    def summary(self) -> str:
        left = self.total - self.done - self.fetched - len(self.failed) - len(self.not_found)
        line = (
            f"{self.done + self.fetched}/{self.total} saqlangan (bu safar {self.fetched}), "
            f"{len(self.failed)} xato, {len(self.not_found)} topilmadi, qoldi {left}"
        )
        return line + (f". To'xtadi: {self.stopped}" if self.stopped else "")


def crawl_scope(
    client: LexClient,
    ws: Workspace,
    items: Iterable[ScopeItem],
    total: int,
    notify: Callable[[str], None] = lambda text: None,
    paused: Callable[[], bool] = lambda: any(unit_active(u) for u in PAUSE_UNITS),
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    say: Callable[[str], None] = print,
    state_file: Path | None = None,
) -> CrawlStats:
    stats = CrawlStats(total=total)
    raw = ws.raw
    streak = 0
    recent_errors: list[float] = []
    last_progress = clock()
    last_pause_check = None

    def save_state() -> None:
        if state_file is not None:
            state_file.write_text(json.dumps(asdict(stats), ensure_ascii=False, indent=1))

    for item in items:
        lex_id = item.lex_id
        if raw.has("docs", lex_id) and raw.has("cards", lex_id) and ws.parsed_path(lex_id).exists():
            stats.done += 1
            continue

        if last_pause_check is None or clock() - last_pause_check >= 60:
            while paused():
                say("nightly update is running, waiting")
                sleep(60)
            last_pause_check = clock()

        try:
            fetch(client, ws, lex_id)
        except NotFound:
            stats.not_found.append(lex_id)
            continue
        except FetchError as exc:
            stats.failed.append({"id": lex_id, "error": str(exc)[:300]})
            say(f"{lex_id:>9}  ERROR {exc}")
            streak += 1
            now = clock()
            recent_errors = [t for t in recent_errors if now - t < 3600] + [now]
            if len(recent_errors) > ERRORS_PER_HOUR:
                stats.stopped = f"bir soatda {len(recent_errors)} ta xato, oxirgisi: {exc}"
                break
            if streak >= ERROR_STREAK:
                say(f"{streak} errors in a row, pausing {ERROR_PAUSE:.0f} s")
                notify(f"Qonunshunos crawl: ketma-ket {streak} ta xato, 10 daqiqa pauza. {exc}")
                sleep(ERROR_PAUSE)
                streak = 0
            continue
        streak = 0
        stats.fetched += 1
        try:
            document, _ = parse(ws, lex_id)
            stats.warnings += len(document.warnings)
        except Exception as exc:  # a parser bug must not stop the download; pages are kept
            stats.failed.append({"id": lex_id, "error": f"parse: {exc}"[:300]})
            say(f"{lex_id:>9}  PARSE ERROR {exc}")
        else:
            say(f"{lex_id:>9}  {item.minor} {item.year}  {item.title[:70]}")

        if clock() - last_progress >= PROGRESS_EVERY:
            notify(f"Qonunshunos crawl: {stats.summary()}")
            last_progress = clock()
        if stats.fetched % 50 == 0:
            save_state()

    save_state()
    return stats
