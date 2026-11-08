"""Tool implementations: database in, Markdown out. Independent of the MCP SDK.

Expected problems (unknown document, missing article) are answered with guidance text, not
errors, so the AI client can recover on its own.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

import psycopg

from qonunshunos.index.doctype import KINDS
from qonunshunos.index.embed import Embed
from qonunshunos.mcp import format as fmt
from qonunshunos.mcp.resolve import (
    ABBREVIATIONS,
    NUMBER_MATCH,
    DocumentRow,
    Resolved,
    abbreviation,
    fetch_documents,
    key,
    looks_like_number,
    normalize_unit_number,
    resolve_by_name,
    resolve_document,
    unit_kinds,
)
from qonunshunos.search.hybrid import search
from qonunshunos.text.normalize import fold

MAX_QUERY = 300
MAX_ALT = 2
SNIPPET = 300  # characters of each search hit
SECTION_COLUMNS = "id, ord, kind, level, number, title, path, elem_id, text, extra"
HEADING_KINDS = ("qism", "boʻlim", "bob", "paragraf", "ilova", "sarlavha")


@dataclass
class SectionRow:
    id: int
    ord: int
    kind: str
    level: int | None
    number: str | None
    title: str | None
    path: list[str]
    elem_id: int | None
    text: str
    extra: dict

    @property
    def is_heading(self) -> bool:
        return self.kind in HEADING_KINDS


@dataclass
class Result:
    """Tool output plus what the usage log needs."""

    text: str
    count: int = 0


# --- shared pieces -------------------------------------------------------------------------


def _doc_line(doc: DocumentRow) -> str:
    """One line like "Mehnat kodeksi — ID -6257288, 28.10.2022, amalda"."""
    parts = [f"ID {doc.id}", fmt.date_uz(doc.adopted_at), fmt.status_uz(doc.status)]
    return f"{doc.display_title} — " + ", ".join(p for p in parts if p)


def _candidates(ref: str, resolved: Resolved) -> Result:
    if not resolved.candidates:
        return Result(
            f"“{ref}” boʻyicha hujjat topilmadi. `find_document` bilan nomi yoki raqami "
            "boʻyicha qidiring yoki `search_law` bilan mazmuni boʻyicha qidiring."
        )
    lines = [f"“{ref}” bir nechta hujjatga mos keladi. Kerakligini ID bilan qayta soʻrang:"]
    lines += [f"- {_doc_line(d)}" for d in resolved.candidates]
    return Result("\n".join(lines), len(resolved.candidates))


def _lost_force(doc: DocumentRow) -> Result:
    card = doc.card or {}
    lines = [
        f"# {doc.display_title}",
        f"Holati: {fmt.status_uz(doc.status)}. Bu hujjatning matni bazada saqlanmaydi.",
    ]
    if card.get("lost_force_at"):
        lines.append(f"Kuchini yoʻqotgan sana: {fmt.date_uz(card['lost_force_at'])}")
    if card.get("lost_force_reason"):
        lines.append(f"Asos: {card['lost_force_reason']}")
    if doc.content == "pdf_only" and doc.in_force:
        lines[1] = "Bu hujjatning matni lex.uz'da hozircha faqat PDF koʻrinishida bor."
    if doc.content == "requisites" and doc.in_force:
        lines[1] = (
            "Bu hujjat boshqa hujjatlarga oʻzgartish kiritadi. Oʻzgartishlar ular kiritilgan "
            "hujjatlarning amaldagi tahririda bor, bu hujjatning oʻz matni bazada saqlanmaydi."
        )
    lines += ["", f"Havola: {doc.url}", fmt.SOURCE]
    return Result("\n".join(lines))


def _document(conn: psycopg.Connection, ref: str) -> DocumentRow | Result:
    """Resolve ``ref`` to a searchable document, or a ready answer explaining why not."""
    resolved = resolve_document(conn, ref)
    if resolved.document is None:
        return _candidates(ref, resolved)
    doc = resolved.document
    if not doc.in_force or doc.content != "html":
        return _lost_force(doc)
    return doc


def _sections(conn: psycopg.Connection, document_id: int, where: str = "", params=()) -> list:
    rows = conn.execute(
        f"SELECT {SECTION_COLUMNS} FROM sections WHERE document_id = %s {where} ORDER BY ord",
        [document_id, *params],
    ).fetchall()
    return [SectionRow(*r) for r in rows]


def _changes_block(extra: dict) -> str | None:
    changes = extra.get("changes") or []
    if not changes:
        return None
    latest = sorted(
        changes,
        key=lambda c: max((link.get("ondate") or "" for link in c.get("links", [])), default=""),
    )[-3:]
    lines = ["Oʻzgartirishlar (oxirgilari):"]
    lines += [f"- {c['text'].strip().strip('()').split(' — ')[0]}" for c in reversed(latest)]
    if len(changes) > 3:
        lines.append(f"- … jami {len(changes)} ta")
    return "\n".join(lines)


def _see_also_block(extra: dict) -> str | None:
    comments = list({c["text"]: c for c in extra.get("comments") or []}.values())[:5]
    if not comments:
        return None
    lines = ["LexUZ sharhi (normativ matn emas):"]
    for comment in comments:
        links = [
            fmt.url(link["doc_id"], link.get("elem_id"))
            for link in comment.get("links", [])
            if link.get("doc_id")
        ]
        lines.append(f"- {comment['text']}" + (f" ({', '.join(links[:2])})" if links else ""))
    return "\n".join(lines)


# --- search_law ----------------------------------------------------------------------------


def search_law(
    conn: psycopg.Connection,
    embedder: Embed,
    query: str,
    alt_queries: Sequence[str] = (),
    doc_types: Sequence[str] | None = None,
    limit: int = 8,
) -> Result:
    query = " ".join(query.split())[:MAX_QUERY]
    alts = [" ".join(q.split())[:MAX_QUERY] for q in alt_queries if q and q.strip()][:MAX_ALT]
    if not query:
        return Result("Soʻrov boʻsh. Savolni oʻzbek tilida (lotin yozuvida) yozing.")
    kinds = [k for k in (doc_types or []) if k in KINDS] or None
    limit = min(max(limit, 1), 15)
    hits = search(conn, embedder, query, alts, doc_types=kinds, limit=limit)
    if not hits:
        return Result(
            "Hech narsa topilmadi. Savolni qonun matnidagi rasmiy iboralar bilan qayta "
            "ifodalab, `alt_queries`ga yozib koʻring."
        )
    lines = []
    for n, hit in enumerate(hits, start=1):
        label = fmt.unit_label(hit.kind, hit.unit_number, hit.unit_title)
        lines.append(f"{n}. {hit.document}, {label}")
        meta = [" > ".join(fmt.clip(p, 50) for p in hit.path[-2:]), fmt.status_uz(hit.status)]
        if hit.last_change_date:
            meta.append(f"hujjat tahriri {fmt.date_uz(hit.last_change_date)}")
        if hit.pending_changes:
            meta.append("⚠ hujjatga oʻzgartirish kiritilmoqda")
        lines.append("   " + " · ".join(m for m in meta if m))
        lines.append(f"   {hit.url}")
        lines.append("   > " + fmt.clip(hit.snippet.replace("\n", " ").rstrip(" …"), SNIPPET))
    top = hits[0]
    article = top.unit_number or ""
    tail = [
        "Parchalar toʻliq emas: javob berishdan oldin moddani oʻqing, masalan "
        f'`get_article(document="{top.document_id}", article="{article}")`.'
    ]
    if not alts:
        tail.append(
            "Maslahat: `alt_queries`ga savolni qonun matnidagi rasmiy iboralar bilan 1–2 marta "
            "qayta yozib bersangiz, natija ancha yaxshilanadi."
        )
    return Result(fmt.join("\n".join(lines), "\n".join(tail), fmt.SOURCE), len(hits))


# --- get_article ---------------------------------------------------------------------------


def get_article(conn: psycopg.Connection, document: str, article: str, page: int = 1) -> Result:
    doc = _document(conn, document)
    if isinstance(doc, Result):
        return doc
    number = normalize_unit_number(article)
    units: list[SectionRow] = []
    for kind in unit_kinds(doc.doc_kind):
        units = _sections(conn, doc.id, "AND kind = %s AND number = %s", [kind, number])
        if units:
            break
    if not units:
        return Result(
            f"{doc.display_title}da “{article}” raqamli modda yoki band topilmadi. "
            f'Mundarijani `get_document(document="{doc.id}")` bilan koʻring yoki '
            "`search_law` bilan mazmuni boʻyicha qidiring."
        )
    if len(units) > 1:
        lines = [f"{doc.display_title}da “{article}” raqamli {len(units)} ta qism bor:"]
        lines += [
            f"- {' > '.join(u.path) or '(asosiy matn)'}: {fmt.unit_label(u.kind, u.number)}"
            f' → `get_section(document="{doc.id}", section="#{u.ord}")`'
            for u in units
        ]
        return Result("\n".join(lines), len(units))
    unit = units[0]
    body = fmt.paginate(unit.text, page)
    call = f'get_article(document="{doc.id}", article="{unit.number}", page={{page}})'
    header = [f"# {doc.display_title}, {fmt.unit_label(unit.kind, unit.number, unit.title)}"]
    if unit.path:
        header.append(" > ".join(unit.path))
    status = f"Holati: {fmt.status_uz(doc.status)}"
    if change := fmt.last_change(unit.extra):
        status += f". Oxirgi oʻzgarish: {change}"
    header += [status, f"Havola: {fmt.url(doc.id, unit.elem_id)}"]
    if note := fmt.pending_note(doc.pending_changes):
        header.append(note)
    last = body.number == body.total
    return Result(
        fmt.join(
            "\n".join(header),
            body.text,
            body.footer(call),
            _changes_block(unit.extra) if last else None,
            _see_also_block(unit.extra) if last else None,
            fmt.SOURCE,
        ),
        1,
    )


# --- get_document --------------------------------------------------------------------------


def _unit_range(units: list[SectionRow]) -> str:
    numbered = [u for u in units if u.number and u.kind in ("modda", "band")]
    if not numbered:
        return ""
    first, last = numbered[0], numbered[-1]
    kind = "moddalar" if first.kind == "modda" else "bandlar"
    if first is last:
        return f"{fmt.unit_label(first.kind, first.number)}"
    return f"{first.number}–{last.number}-{kind}"


def _under(heading: SectionRow, unit: SectionRow) -> bool:
    depth = len(heading.path)
    return unit.path[:depth] == heading.path and unit.path[depth : depth + 1] == [heading.text]


def table_of_contents(sections: list[SectionRow]) -> list[str]:
    units = [s for s in sections if not s.is_heading]
    lines = []
    for heading in (s for s in sections if s.is_heading):
        span = _unit_range([u for u in units if _under(heading, u)])
        indent = "  " * len(heading.path)
        lines.append(f"{indent}- [#{heading.ord}] {heading.text}" + (f" — {span}" if span else ""))
    return lines


def _requisites(doc: DocumentRow) -> list[str]:
    card = doc.card or {}
    rows = [
        ("Turi", doc.doc_kind),
        ("Raqami", doc.number),
        ("Qabul qilingan", fmt.date_uz(doc.adopted_at)),
        ("Kuchga kirgan", fmt.date_uz(card.get("entry_into_force"))),
        ("Holati", fmt.status_uz(doc.status)),
        ("Kuchini yoʻqotgan", fmt.date_uz(card.get("lost_force_at"))),
        ("Qabul qilgan organ", doc.accepting_body or _organ(card)),
        ("Joriy tahrir", fmt.date_uz(doc.edition_date)),
        ("Oxirgi oʻzgarish", fmt.date_uz(doc.last_change_date)),
        ("Havola", doc.url),
    ]
    return [f"{name}: {value}" for name, value in rows if value]


# card1 sometimes arrives in Russian; the most common issuing bodies in Uzbek.
ORGANS_UZ = {
    "Олий Мажлис Республики Узбекистан": "Oʻzbekiston Respublikasi Oliy Majlisi",
    "Президент Республики Узбекистан": "Oʻzbekiston Respublikasi Prezidenti",
    "Кабинет Министров Республики Узбекистан": "Oʻzbekiston Respublikasi Vazirlar Mahkamasi",
    "Ўзбекистон Республикаси Олий Мажлиси": "Oʻzbekiston Respublikasi Oliy Majlisi",
    "Ўзбекистон Республикаси Президенти": "Oʻzbekiston Respublikasi Prezidenti",
    "Ўзбекистон Республикаси Вазирлар Маҳкамаси": "Oʻzbekiston Respublikasi Vazirlar Mahkamasi",
}


def _organ(card: dict) -> str | None:
    bodies = card.get("bodies") or []
    organ = bodies[0].get("organ") if bodies else None
    return ORGANS_UZ.get(organ, organ) if organ else None


def get_document(conn: psycopg.Connection, document: str, page: int = 1) -> Result:
    resolved = resolve_document(conn, document)
    if resolved.document is None:
        return _candidates(document, resolved)
    doc = resolved.document
    header = [f"# {doc.display_title}", f"Toʻliq nomi: {doc.title}", *_requisites(doc)]
    if note := fmt.pending_note(doc.pending_changes):
        header.append(note)
    if not doc.in_force or doc.content != "html":
        return Result(fmt.join("\n".join(header), "Bu hujjatning matni bazada yoʻq.", fmt.SOURCE))
    sections = _sections(conn, doc.id)
    toc = table_of_contents(sections)
    units = sum(1 for s in sections if not s.is_heading)
    if not toc:
        toc = [f"Bu hujjatda boʻlim va boblar yoʻq: {units} ta modda yoki band."]
    body = fmt.paginate("\n".join(toc), page)
    hint = (
        f'Bob yoki boʻlim matni: `get_section(document="{doc.id}", section="#N")`. '
        f'Modda: `get_article(document="{doc.id}", article="…")`.'
    )
    call = f'get_document(document="{doc.id}", page={{page}})'
    return Result(
        fmt.join("\n".join(header), "Mundarija:\n" + body.text, body.footer(call), hint),
        units,
    )


# --- get_section ---------------------------------------------------------------------------

_LABEL_RE = re.compile(r"^\s*([0-9IVXLCDM]+|umumiy|maxsus)\s*[-–. ]?\s*(\w+)", re.IGNORECASE)
_KIND_WORDS = {
    "bob": "bob",
    "bobi": "bob",
    "bolim": "boʻlim",
    "bolimi": "boʻlim",
    "qism": "qism",
    "qismi": "qism",
    "paragraf": "paragraf",
    "ilova": "ilova",
    "ilovasi": "ilova",
}


def _find_heading(sections: list[SectionRow], ref: str) -> list[SectionRow]:
    headings = [s for s in sections if s.is_heading]
    ref = ref.strip()
    if m := re.fullmatch(r"#?\s*(\d+)", ref):
        return [h for h in headings if h.ord == int(m[1])]
    if m := _LABEL_RE.match(ref):
        kind = _KIND_WORDS.get(fold(m[2]).replace("ʻ", "").replace("'", ""))
        if kind:
            number = m[1].upper() if not m[1].isdigit() else m[1]
            found = [h for h in headings if h.kind == kind and (h.number or "").upper() == number]
            if found:
                return found
    needle = fold(ref)
    return [h for h in headings if needle and needle in fold(h.text)]


def get_section(conn: psycopg.Connection, document: str, section: str, page: int = 1) -> Result:
    doc = _document(conn, document)
    if isinstance(doc, Result):
        return doc
    sections = _sections(conn, doc.id)
    found = _find_heading(sections, section)
    if not found:
        return Result(
            f"{doc.display_title}da “{section}” boʻlimi topilmadi. Mundarijani "
            f'`get_document(document="{doc.id}")` bilan koʻring va `section="#N"` bering.'
        )
    if len(found) > 1:
        lines = [f"“{section}” bir nechta boʻlimga mos keladi:"]
        lines += [f"- [#{h.ord}] {' > '.join([*h.path, h.text])}" for h in found[:10]]
        return Result("\n".join(lines), len(found))
    heading = found[0]
    parts = []
    count = 0
    for s in sections:
        if s.ord <= heading.ord:
            continue
        if s.is_heading and not _under(heading, s):
            break
        if s.is_heading:
            parts.append(f"## {s.text}")
        elif _under(heading, s):
            count += 1
            label = fmt.unit_label(s.kind, s.number, s.title)
            parts.append(f"### {label}\n{fmt.url(doc.id, s.elem_id)}\n{s.text}")
    body = fmt.paginate("\n\n".join(parts) or "(Bu boʻlimda matn yoʻq.)", page)
    call = f'get_section(document="{doc.id}", section="#{heading.ord}", page={{page}})'
    title = " > ".join([*heading.path, heading.text])
    return Result(
        fmt.join(
            f"# {doc.display_title}: {title}\nHavola: {fmt.url(doc.id, heading.elem_id)}",
            fmt.pending_note(doc.pending_changes),
            body.text,
            body.footer(call),
            fmt.SOURCE,
        ),
        count,
    )


# --- find_document -------------------------------------------------------------------------


def find_document(
    conn: psycopg.Connection,
    query: str,
    doc_type: str | None = None,
    year: int | None = None,
    include_lost_force: bool = False,
    limit: int = 10,
) -> Result:
    query = " ".join(query.split())[:MAX_QUERY]
    limit = min(max(limit, 1), 20)
    where, params = ["TRUE"], []
    if doc_type in KINDS:
        where.append("doc_kind = %s")
        params.append(doc_type)
    if year:
        where.append("extract(year FROM adopted_at) = %s")
        params.append(year)
    if not include_lost_force:
        where.append("status = 'in_force'")
    found: list[DocumentRow] = []
    number = key(query)
    if number and any(c.isdigit() for c in number):
        found = fetch_documents(
            conn,
            " AND ".join([*where, NUMBER_MATCH]),
            [*params, number],
            "ORDER BY adopted_at DESC NULLS LAST",
            limit,
        )
    if not found and query and not looks_like_number(query):
        abbr = abbreviation(query)
        name = resolve_by_name(conn, abbr or query, " AND ".join(where), params, limit)
        found = [name.document] if name.document else name.candidates
    if not found:
        return Result(
            f"“{query}” boʻyicha hujjat topilmadi. Mazmuni boʻyicha `search_law` bilan "
            "qidirib koʻring. Eng yangi hujjatlar bazaga hali qoʻshilmagan boʻlishi mumkin."
        )
    lines = [f"{n}. {_doc_line(d)}\n   {d.url}" for n, d in enumerate(found, start=1)]
    return Result(fmt.join("\n".join(lines), fmt.SOURCE), len(found))


# --- list_codes ----------------------------------------------------------------------------


def list_codes(conn: psycopg.Connection) -> Result:
    docs = fetch_documents(
        conn,
        "doc_kind IN ('konstitutsiya', 'kodeks') AND status = 'in_force'",
        [],
        "ORDER BY doc_kind DESC, display_title",
        limit=100,
    )
    lines = []
    for doc in docs:
        abbr = next((a for a, t in ABBREVIATIONS.items() if doc.display_title.startswith(t)), None)
        edition = fmt.date_uz(doc.edition_date or doc.last_change_date)
        meta = [f"ID {doc.id}", f"qisqartma {abbr}" if abbr else ""]
        if edition:
            meta.append(f"tahrir {edition}")
        lines.append(f"- {doc.display_title} — " + ", ".join(m for m in meta if m))
    return Result(
        fmt.join(f"Amaldagi kodekslar ({len(docs)} ta):", "\n".join(lines), fmt.SOURCE),
        len(docs),
    )
