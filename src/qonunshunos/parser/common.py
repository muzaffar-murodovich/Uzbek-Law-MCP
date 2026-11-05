"""Helpers shared by lex.uz page parsers."""

import re
from datetime import date

from bs4 import Comment as BsComment
from bs4 import NavigableString, Tag

from qonunshunos.parser.models import Link
from qonunshunos.text.normalize import normalize_text, to_superscript

_LINK_RE = re.compile(
    r"^(?:https?://(?:www\.)?lex\.uz)?(?:/[a-z]{2})?/docs/(?P<doc>-?\d+)"
    r"(?:\?(?P<query>[^#]*))?(?:#(?P<elem>-?\d+))?"
)
_ONDATE_RE = re.compile(r"ONDATE=(\d{2}\.\d{2}\.\d{4})")
_DMY_RE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$")

UZ_MONTHS = {
    "yanvar": 1,
    "fevral": 2,
    "mart": 3,
    "aprel": 4,
    "may": 5,
    "iyun": 6,
    "iyul": 7,
    "avgust": 8,
    "sentabr": 9,
    "oktabr": 10,
    "noyabr": 11,
    "dekabr": 12,
}
_UZ_DATE_RE = re.compile(r"(\d{4})-yil\s+(\d{1,2})-(" + "|".join(UZ_MONTHS) + r")", re.IGNORECASE)


def dmy_to_iso(value: str | None) -> str | None:
    """``"04.11.2026"`` → ``"2026-11-04"``; anything else → None."""
    if not value:
        return None
    m = _DMY_RE.match(value.strip())
    if not m:
        return None
    day, month, year = (int(x) for x in m.groups())
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def uz_date_to_iso(value: str) -> str | None:
    """``"2022-yil 28-yanvar"`` → ``"2022-01-28"``."""
    m = _UZ_DATE_RE.search(value)
    if not m:
        return None
    year, day, month = int(m.group(1)), int(m.group(2)), UZ_MONTHS[m.group(3).lower()]
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def parse_link(href: str, text: str = "") -> Link | None:
    m = _LINK_RE.match(href.strip())
    if not m:
        return None
    ondate = _ONDATE_RE.search(m.group("query") or "")
    elem = m.group("elem")
    return Link(
        doc_id=int(m.group("doc")),
        elem_id=int(elem) if elem else None,
        ondate=dmy_to_iso(ondate.group(1)) if ondate else None,
        text=normalize_text(text),
    )


def links_of(tag: Tag) -> list[Link]:
    links = []
    for a in tag.find_all("a", href=True):
        link = parse_link(a["href"], a.get_text())
        if link is not None:
            links.append(link)
    return links


def replace_superscripts(root: Tag) -> None:
    """Turn ``5<sup>1</sup>`` into ``5¹`` in place."""
    for sup in root.find_all("sup"):
        sup.replace_with(to_superscript(sup.get_text()))


_BLOCK_TAGS = {"p", "div", "br", "td", "th", "tr", "li", "table", "ul", "ol", "h1", "h2", "h3"}


def text_of(tag: Tag) -> str:
    """Text of an element: inline tags are joined as is, block tags are separated by a space."""
    parts: list[str] = []
    for node in tag.descendants:
        if isinstance(node, NavigableString):
            if not isinstance(node, BsComment):
                parts.append(str(node))
        elif node.name in _BLOCK_TAGS:
            parts.append(" ")
    return normalize_text("".join(parts))


def element_id(value: str | None) -> int | None:
    """``"-6257549"`` → -6257549; ids like ``"edi-…"`` or ``"onLBC-…"`` → None."""
    if value and re.fullmatch(r"-?\d+", value):
        return int(value)
    return None
