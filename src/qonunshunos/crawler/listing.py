"""lex.uz search listings (``/uz/search/nat?...``) with ASP.NET postback paging."""

import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from qonunshunos.crawler.client import LexClient
from qonunshunos.text.normalize import normalize_text

NEXT_PAGE_TARGET = "ucFoundActsControl$LinkButton1"
FORM_LISTING = "/uz/search/nat?lang=4&fform_id="
CODES_LISTING = f"{FORM_LISTING}3964"

_DOC_HREF_RE = re.compile(r"/docs/(-?\d+)")
_TOTAL_RE = re.compile(r"(\d[\d\s]*)\s+hujjat topildi")


@dataclass
class ListingRow:
    position: int | None
    lex_id: int
    title: str
    badge: str | None
    in_force: bool | None  # status_code_y → True, status_code_r → False


@dataclass
class ListingPage:
    rows: list[ListingRow]
    total: int | None
    has_next: bool
    form: dict[str, str] = field(default_factory=dict)  # hidden ASP.NET fields


def parse_listing(html: str) -> ListingPage:
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for tr in soup.select("tr.dd-table__main-item"):
        link = tr.select_one(".dd-table__main-left-desc a[href]")
        m = _DOC_HREF_RE.search(link["href"]) if link else None
        if link is None or m is None:
            continue
        number = tr.select_one(".dd-table__main-item_number")
        badge = tr.select_one(".dd-table__main-extra .badge")
        icon = tr.select_one(".lx_act_state i")
        icon_classes = set(icon.get("class", [])) if icon else set()
        in_force = (
            True
            if "status_code_y" in icon_classes
            else False
            if "status_code_r" in icon_classes
            else None
        )
        position_text = number.get_text(strip=True) if number else ""
        rows.append(
            ListingRow(
                position=int(position_text) if position_text.isdigit() else None,
                lex_id=int(m.group(1)),
                title=normalize_text(link.get_text()),
                badge=normalize_text(badge.get_text()) if badge else None,
                in_force=in_force,
            )
        )

    total_match = _TOTAL_RE.search(soup.get_text(" "))
    total = int(re.sub(r"\s", "", total_match.group(1))) if total_match else None
    next_link = soup.find("a", id="ucFoundActsControl_LinkButton1", href=True)
    form = {}
    for name in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"):
        field_tag = soup.find("input", attrs={"name": name})
        if field_tag is not None:
            form[name] = field_tag.get("value", "")
    return ListingPage(rows=rows, total=total, has_next=next_link is not None, form=form)


def iter_pages(client: LexClient, path: str, max_pages: int = 10_000) -> Iterator[ListingPage]:
    """Yield every page of a listing, following "Keyingisi" postbacks."""
    page = parse_listing(client.get(path).text)
    seen = 0
    for _ in range(max_pages):
        yield page
        seen += len(page.rows)
        if not page.has_next or not page.rows or (page.total is not None and seen >= page.total):
            return
        data = {**page.form, "__EVENTTARGET": NEXT_PAGE_TARGET, "__EVENTARGUMENT": ""}
        page = parse_listing(client.post(path, data).text)


def iter_listing(client: LexClient, path: str, max_pages: int = 10_000) -> Iterator[ListingRow]:
    """Yield every row of a listing."""
    for page in iter_pages(client, path, max_pages):
        yield from page.rows


def read_listing(
    client: LexClient, path: str, max_pages: int = 10_000
) -> tuple[list[ListingRow], int | None]:
    """All rows of a listing and the number of documents lex.uz says it has."""
    rows, total = [], None
    for page in iter_pages(client, path, max_pages):
        rows.extend(page.rows)
        total = page.total if total is None else total
    return rows, total
