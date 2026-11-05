"""lex.uz document page (``/docs/-{id}``) → :class:`ParsedDocument`.

The text lives in ``#divCont`` as a flat sequence of blocks; each block's class tells what it is
(see docs/research/lexuz.md, sections 4 and 8). The blocks are read once, in order.
"""

import re
from collections import Counter

from bs4 import BeautifulSoup, Tag

from qonunshunos.parser.common import (
    dmy_to_iso,
    element_id,
    links_of,
    replace_superscripts,
    text_of,
    uz_date_to_iso,
)
from qonunshunos.parser.models import (
    Change,
    Comment,
    Heading,
    HeadingKind,
    Paragraph,
    ParsedDocument,
    Table,
    Unit,
    UnitKind,
)
from qonunshunos.text.normalize import fold, normalize_text


class ParseError(ValueError):
    pass


_SUP = "⁰¹²³⁴⁵⁶⁷⁸⁹"
_ARTICLE_RE = re.compile(rf"^(\d+[{_SUP}]*)\s*-\s*modda\.?\s*(.*)$")
_BAND_RE = re.compile(rf"^(\d+[{_SUP}]*)\.\s+\S")
_TITLE_RE = re.compile(
    r"^(?:(?P<number>\S+?)-сон\s+)?(?P<date>\d{2}\.\d{2}\.\d{4})\.\s*(?P<title>.+)$"
)
_LANG_BUTTONS = {"рус": "ru", "ўзб": "uz-Cyrl", "eng": "en", "o’zb": "uz-Latn", "oʻzb": "uz-Latn"}
_OPEN_URL_RE = re.compile(r"openUrl\('/docs/(-?\d+)'\)")
_INDEX_ID_RE = re.compile(r"^on(LBC|LS)(-?\d+)$")
_APPENDIX_RE = re.compile(r"(?:(\w+ga)\s+)?(\d+)\s*-\s*ilova\b", re.IGNORECASE)
_MAIN_ACT_OWNERS = ("qaror", "farmon", "farmoyish", "qonun", "buyrugʻ", "kodeks")

_SKIP = {"NEW_EDITION", "OFFICIAL_SOUR_TEXT"}  # the latter: link to a PDF
_HEADINGS = {"TEXT_HEADER_DEFAULT", "TEXT_BOLD_CENTER", "TEXT_CENTER", "TEXT_HEADER_AFTER_SRC"}
# Adoption stamps of laws ("Qonunchilik palatasi tomonidan ... qabul qilingan").
_NOTES = {"GRIF_PARLAMENT", "TEXT_RIGHT"}
_QUOTES = "“”\"«„'"
_CONTENT = {"ACT_TEXT", "FOOTNOTE"}

# (regex on folded heading text, level, kind)
_HEADING_LEVELS: list[tuple[re.Pattern[str], int, HeadingKind]] = [
    (re.compile(r"^(?P<n>\S+)\s+qism\b"), 1, "qism"),
    (re.compile(r"^(?P<n>\S+)\s+boʻlim\b"), 2, "boʻlim"),
    (re.compile(r"^(?P<n>\d+[" + _SUP + r"]*|[ivxlcdm]+)(?:-|\s+)bob\b"), 3, "bob"),
    (re.compile(r"^(?P<n>\d+[" + _SUP + r"]*)-§|^(?P<n2>\S+)\s+paragraf\b"), 4, "paragraf"),
]


def classify_heading(text: str) -> tuple[int, HeadingKind, str | None, str]:
    """Return (level, kind, number, title) for a heading line."""
    folded = fold(text)
    for pattern, level, kind in _HEADING_LEVELS:
        m = pattern.match(folded)
        if m:
            number = next((g for g in m.groups() if g), None)
            # Keep the original case of the number ("I", "1").
            if number is not None:
                number = text[: len(number)]
            _, _, title = text.partition(". ")
            return level, kind, number, title.strip() or text
    return 5, "sarlavha", None, text


class _State:
    def __init__(self, doc: ParsedDocument, has_articles: bool) -> None:
        self.doc = doc
        self.has_articles = has_articles
        self.stack: list[Heading] = []
        self.unit: Unit | None = None
        self.pending_okoz: list[str] = []
        self.seen_structure = False  # any heading or unit so far
        self.appendix_title_open = False
        self.unknown: Counter[str] = Counter()

    def path(self) -> list[str]:
        return [h.text for h in self.stack]

    def new_unit(self, kind: UnitKind, elem_id: int | None, **kwargs: str | None) -> Unit:
        unit = Unit(kind=kind, elem_id=elem_id, path=self.path(), **kwargs)
        self.doc.units.append(unit)
        self.unit = unit
        self.seen_structure = True
        return unit

    def content_unit(self, elem_id: int | None) -> Unit:
        """The unit that receives free text; opens a "kirish"/"matn" unit if needed."""
        if self.unit is None:
            self.new_unit("matn" if self.seen_structure else "kirish", elem_id)
        assert self.unit is not None
        self.attach_okoz(self.unit)
        return self.unit

    def attach_okoz(self, unit: Unit) -> None:
        for code in self.pending_okoz:
            if code not in unit.okoz:
                unit.okoz.append(code)
        self.pending_okoz.clear()

    def push_heading(self, heading: Heading) -> None:
        while self.stack and self.stack[-1].level >= heading.level:
            self.stack.pop()
        self.stack.append(heading)
        self.doc.headings.append(heading)
        self.unit = None
        self.seen_structure = True


def _inner(block: Tag) -> Tag:
    """The ``div[id]`` that holds a block's text (the rest are interface buttons)."""
    inner = block.find("div", id=True, recursive=False)
    return inner if inner is not None else block


def _parse_title(raw: str) -> tuple[str, str | None, str | None]:
    text = normalize_text(raw)
    m = _TITLE_RE.match(text)
    if not m:
        return text, None, None
    return m.group("title"), m.group("number"), dmy_to_iso(m.group("date"))


def _parse_index(inner: Tag) -> list[str]:
    return [
        normalize_text(v.get_text()).rstrip("]").strip()
        for v in inner.select(".iorVal")
        if v.get_text(strip=True)
    ]


def _parse_table(block: Tag, elem_id: int | None) -> Table:
    rows = []
    for tr in block.find_all("tr"):
        cells = [text_of(td) for td in tr.find_all(["td", "th"], recursive=False)]
        if any(cells):
            rows.append(cells)
    return Table(elem_id=elem_id, rows=rows)


def _appendix_heading(text: str, elem_id: int | None) -> Heading:
    m = _APPENDIX_RE.search(text)
    if m is None:
        label, number = "Ilova", None
    else:
        owner, number = m.group(1), m.group(2)
        label = f"{number}-ilova"
        if owner and not fold(owner).startswith(_MAIN_ACT_OWNERS):
            label = f"{owner[0].upper()}{owner[1:]} {label}"
    return Heading(elem_id=elem_id, level=0, kind="ilova", number=number, title=label, text=label)


def _handle_block(state: _State, cls: str, block: Tag, no_select: bool) -> None:
    doc = state.doc
    inner = _inner(block)
    raw_id = inner.get("id") if inner is not block else block.get("id")
    elem_id = element_id(raw_id if isinstance(raw_id, str) else None)
    text = text_of(inner)

    # ACT_FORM right after ACT_TITLE_APPL ("NIZOM", "ROʻYXATI") completes the appendix title.
    appendix_title_open = state.appendix_title_open
    state.appendix_title_open = False

    if cls in _SKIP:
        return

    if cls == "INDEXES_ON_REF":
        m = _INDEX_ID_RE.match(str(raw_id or ""))
        codes = _parse_index(inner)
        if m and int(m.group(2)) == doc.lex_id:
            (doc.okoz if m.group(1) == "LBC" else doc.tsz).extend(codes)
        elif m and m.group(1) == "LBC":
            state.pending_okoz.extend(codes)
        return

    if cls in ("COMMENT", "EXPLANATION"):  # editorial notes, not normative text
        if str(raw_id or "").startswith("edi") or text.startswith("Oldingi tahrirga"):
            return
        comment = Comment(elem_id=elem_id, text=text, links=links_of(inner))
        (state.unit.comments if state.unit else doc.comments).append(comment)
        return

    if cls == "CHANGES_ORIGINS":
        change = Change(elem_id=elem_id, text=text, links=links_of(inner))
        (state.unit.changes if state.unit else doc.changes).append(change)
        return

    if cls == "PUBLICATION_ORIGIN":
        doc.publication_origin = text
        return

    if cls == "ACCEPTING_BODY":
        doc.accepting_body = text
        return

    if cls == "ACT_TITLE":
        if not doc.title:
            doc.title = text
        return

    if cls == "ACT_FORM":
        if appendix_title_open and text and state.stack:
            head = state.stack[-1]
            head.text = f"{head.text} {text}"
        return

    if cls == "SIGNATURE":
        doc.signature = text
        state.unit = None
        return

    if cls == "ACT_ESSENTIAL_ELEMENTS":
        value = text.rstrip(",").strip()
        iso = uz_date_to_iso(value)
        if iso:
            doc.signed_date = iso
        elif value and doc.signed_place is None:
            doc.signed_place = value
        state.unit = None
        return

    if cls == "ACT_ESSENTIAL_ELEMENTS_NUM":
        doc.signed_number = re.sub(r"-son$", "", text.rstrip(",").strip())
        state.unit = None
        return

    if cls == "APPL_BANNER_LANDSCAPE_TITLE":
        state.push_heading(_appendix_heading(text, elem_id))
        return

    if cls == "ACT_TITLE_APPL":
        if state.stack and state.stack[-1].kind == "ilova":
            head = state.stack[-1]
            head.text = f"{head.text}. {text}"
            state.appendix_title_open = True
        else:
            state.push_heading(
                Heading(
                    elem_id=elem_id, level=5, kind="sarlavha", number=None, title=text, text=text
                )
            )
        return

    if cls in _NOTES:
        if text:
            doc.notes.append(text)
        return

    if cls in _HEADINGS:
        if not text:
            return
        if cls == "TEXT_CENTER" and no_select:
            doc.notes.append(text)
            return
        level, kind, number, title = classify_heading(text)
        if level == 5 and state.unit is not None and state.unit.kind == "modda":
            # A minor heading inside an article (e.g. above a table) stays part of the article.
            state.unit.paragraphs.append(Paragraph(elem_id=elem_id, text=text))
            return
        state.push_heading(
            Heading(elem_id=elem_id, level=level, kind=kind, number=number, title=title, text=text)
        )
        return

    if cls == "CLAUSE_DEFAULT":
        if not text:
            return
        if text[0] in _QUOTES and state.unit is not None:
            # An article quoted inside an amending provision ("“67²-modda. ...”") is text.
            state.unit.paragraphs.append(Paragraph(elem_id=elem_id, text=text))
            return
        m = _ARTICLE_RE.match(text)
        if m:
            unit = state.new_unit("modda", elem_id, number=m.group(1), title=m.group(2) or None)
        else:
            doc.warnings.append(f"unrecognised article heading {elem_id}: {text[:60]}")
            unit = state.new_unit("modda", elem_id, title=text)
        state.attach_okoz(unit)
        return

    if cls.startswith("TABLE_") or cls == "BY_DEFAULT":
        table = inner.find("table")
        if table is not None:
            state.content_unit(elem_id).tables.append(_parse_table(table, elem_id))
        elif text:
            state.content_unit(elem_id).paragraphs.append(
                Paragraph(elem_id=elem_id, text=text, links=links_of(inner))
            )
        return

    if cls in _CONTENT:
        if not text:
            return
        m = _BAND_RE.match(text) if cls == "ACT_TEXT" and not state.has_articles else None
        if m:
            unit = state.new_unit("band", elem_id, number=m.group(1))
            state.attach_okoz(unit)
        else:
            unit = state.content_unit(elem_id)
        table = inner.find("table")
        if table is not None:
            unit.tables.append(_parse_table(table, elem_id))
        else:
            unit.paragraphs.append(Paragraph(elem_id=elem_id, text=text, links=links_of(inner)))
        return

    state.unknown[cls] += 1


def _alternates(soup: BeautifulSoup) -> dict[str, int]:
    result = {}
    for button in soup.select(".docContentHeader__item-link"):
        lang = _LANG_BUTTONS.get(button.get_text(strip=True).lower())
        m = _OPEN_URL_RE.search(str(button.get("onclick", "")))
        if lang and m:
            result[lang] = int(m.group(1))
    return result


def parse_document(html: str, lex_id: int, url: str | None = None) -> ParsedDocument:
    soup = BeautifulSoup(html, "lxml")
    title_tag = soup.find("title")
    title, number, adopted = _parse_title(title_tag.get_text() if title_tag else "")
    cont = soup.find(id="divCont")
    if cont is None and soup.find(id="pdfBody") is None:
        raise ParseError(f"no #divCont or #pdfBody in document {lex_id}")

    doc = ParsedDocument(
        lex_id=lex_id,
        url=url or f"https://lex.uz/docs/{lex_id}",
        content="html" if cont is not None else "pdf_only",
        title=title,
        number=number,
        date=adopted,
        alternates=_alternates(soup),
    )
    edition = soup.select_one("#lx_var_t .lx_date_selected")
    if edition is not None:
        doc.edition_date = dmy_to_iso(edition.get_text(strip=True))
    if cont is None:
        return doc

    replace_superscripts(cont)
    blocks = cont.find_all(recursive=False)
    has_articles = any("CLAUSE_DEFAULT" in b.get("class", []) for b in blocks)
    state = _State(doc, has_articles)
    for block in blocks:
        classes = [c for c in block.get("class", []) if not c.startswith("lx_")]
        if not classes:
            continue
        _handle_block(state, classes[0], block, "lx_no_select" in block.get("class", []))

    change_dates = [
        link.ondate
        for changes in [doc.changes, *(u.changes for u in doc.units)]
        for change in changes
        for link in change.links
        if link.ondate
    ]
    doc.last_change_date = max(change_dates, default=None)

    if state.pending_okoz:
        doc.warnings.append(f"{len(state.pending_okoz)} OKOZ entries not attached to any unit")
    for cls, count in sorted(state.unknown.items()):
        doc.warnings.append(f"unknown block class {cls} ×{count}")
    return doc
