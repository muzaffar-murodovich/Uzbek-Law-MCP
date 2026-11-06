"""Compact Markdown for tool results (read by an AI client, so every token counts)."""

import datetime as dt
from dataclasses import dataclass

LEX_BASE = "https://lex.uz/docs"
PAGE_SIZE = 9000  # characters (≈2000 tokens)
SOURCE = "Manba: lex.uz (Qonunchilik maʼlumotlari milliy bazasi)"

STATUS_UZ = {
    "in_force": "amalda",
    "lost_force": "kuchini yoʻqotgan",
    "not_in_force": "kuchga kirmagan",
    "unknown": "holati nomaʼlum",
}


def status_uz(status: str) -> str:
    return STATUS_UZ.get(status, status)


def date_uz(value: object) -> str:
    """ISO date → "28.10.2022"; empty for ``None``."""
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        try:
            value = dt.date.fromisoformat(value[:10])
        except ValueError:
            return value
    return value.strftime("%d.%m.%Y") if isinstance(value, dt.date) else str(value)


def url(document_id: int, elem_id: int | None = None) -> str:
    return f"{LEX_BASE}/{document_id}" + (f"#{elem_id}" if elem_id is not None else "")


def unit_label(kind: str, number: str | None, title: str | None = None) -> str:
    """Label like "161-modda. Mehnat shartnomasini …", "5-band" or "Kirish qismi"."""
    if kind in ("modda", "band") and number:
        label = f"{number}-{kind}"
    elif kind == "kirish":
        label = "Kirish qismi"
    else:
        label = ""
    if title:
        return f"{label}. {title}" if label else title
    return label or kind


def last_change(extra: dict) -> str | None:
    """Latest "… tahririda" note of a unit, without the publication details."""
    changes = extra.get("changes") or []
    if not changes:
        return None

    def when(change: dict) -> str:
        return max((link.get("ondate") or "" for link in change.get("links", [])), default="")

    note = max(changes, key=when)["text"]
    return note.strip().strip("()").split(" — ")[0].strip()


@dataclass
class Page:
    text: str
    number: int
    total: int

    def footer(self, call: str) -> str:
        """Paging line like "2/3-sahifa. Keyingisi: …" (empty for a single page)."""
        if self.total <= 1:
            return ""
        line = f"{self.number}/{self.total}-sahifa."
        if self.number < self.total:
            line += f" Keyingisi: {call.format(page=self.number + 1)}"
        return line


def paginate(text: str, page: int = 1, size: int = PAGE_SIZE) -> Page:
    """Split at line boundaries into pages of at most ``size`` characters (long lines are cut)."""
    pages: list[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > size:
            if current:
                pages.append(current)
                current = ""
            cut = line.rfind(" ", 0, size)
            cut = cut if cut > size // 2 else size
            pages.append(line[:cut])
            line = line[cut:].lstrip()
        if current and len(current) + 1 + len(line) > size:
            pages.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current or not pages:
        pages.append(current)
    total = len(pages)
    number = min(max(page, 1), total)
    return Page(pages[number - 1], number, total)


def clip(text: str, size: int) -> str:
    """Cut at a word boundary and mark the cut with "…"."""
    text = " ".join(text.split())
    if len(text) <= size:
        return text
    cut = text[: size - 1].rsplit(" ", 1)[0]
    return f"{cut} …"


def join(*blocks: str | None) -> str:
    """Non-empty blocks separated by blank lines."""
    return "\n\n".join(b.strip("\n") for b in blocks if b and b.strip())
