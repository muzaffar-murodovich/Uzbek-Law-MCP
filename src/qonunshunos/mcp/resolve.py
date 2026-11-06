"""Turn what an AI client writes ("MK", "OʻRQ-642", a lex.uz URL, "161-modda") into rows."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

import psycopg

from qonunshunos.text.normalize import fold, to_superscript

# Common abbreviations → start of the display title. Lookup ignores case and spaces.
ABBREVIATIONS = {
    "MK": "Mehnat kodeksi",
    "JK": "Jinoyat kodeksi",
    "JPK": "Jinoyat-protsessual kodeksi",
    "JIK": "Jinoyat-ijroiya kodeksi",
    "FK": "Fuqarolik kodeksi",
    "FPK": "Fuqarolik protsessual kodeksi",
    "IPK": "Iqtisodiy protsessual kodeksi",
    "MJtK": "Maʼmuriy javobgarlik",
    "MSIYuK": "Maʼmuriy sud ishlarini",
    "SK": "Soliq kodeksi",
    "BK": "Bojxona kodeksi",
    "BudK": "Budjet kodeksi",
    "OK": "Oila kodeksi",
    "UJK": "Uy-joy kodeksi",
    "YK": "Yer kodeksi",
    "HK": "Havo kodeksi",
    "ShK": "Shaharsozlik kodeksi",
}
_ALIASES = {"mjk": "MJtK", "msiyk": "MSIYuK", "konstitutsiya": None}


def abbreviation(text: str) -> str | None:
    """Title prefix for an abbreviation ("mk", "MJtK", "Konstitutsiya"), else ``None``."""
    word = fold(text).replace("ʻ", "").replace(" ", "")
    if word == "konstitutsiya":
        return "Oʻzbekiston Respublikasi Konstitutsiyasi"
    word = (_ALIASES.get(word) or word).lower()
    return next((t for a, t in ABBREVIATIONS.items() if a.lower() == word), None)


DOC_COLUMNS = (
    "id, title, display_title, doc_kind, number, adopted_at, status, accepting_body, url,"
    " content, edition_date, last_change_date, card"
)


@dataclass
class DocumentRow:
    id: int
    title: str
    display_title: str
    doc_kind: str
    number: str | None
    adopted_at: object
    status: str
    accepting_body: str | None
    url: str
    content: str
    edition_date: object
    last_change_date: object
    card: dict | None

    @property
    def in_force(self) -> bool:
        return self.status == "in_force"


@dataclass
class Resolved:
    """Exactly one document, or candidates when the reference was ambiguous or unknown."""

    document: DocumentRow | None
    candidates: list[DocumentRow]
    elem_id: int | None = None  # "#-6257549" in a lex.uz URL


_URL_RE = re.compile(r"lex\.uz/(?:\w+/)?docs/(-?\d+)(?:[^#\s]*#(-?\d+))?")
_ID_RE = re.compile(r"^\s*(-?\d{3,9})\s*$")


NUMBER_MATCH = "regexp_replace(lower(number), '[^0-9a-zа-яёқғўҳ]', '', 'g') = %s"


def looks_like_number(text: str) -> bool:
    """ "PF-60", "OʻRQ-642", "897", "349-I": a short reference with digits, not a name."""
    words = text.split()
    return any(c.isdigit() for c in text) and len(words) <= 2 and len(text) <= 20


def key(text: str) -> str:
    """Comparison key for document numbers: "OʻRQ-642", "orq 642", "ОʻРҚ–642" → "orq642"."""
    return re.sub(r"[^0-9a-zа-яёқғўҳ]", "", fold(text))


def fetch_documents(
    conn: psycopg.Connection, where: str, params: Sequence, order: str = "", limit: int = 5
) -> list[DocumentRow]:
    rows = conn.execute(
        f"SELECT {DOC_COLUMNS} FROM documents WHERE {where} {order} LIMIT {int(limit)}", params
    ).fetchall()
    return [DocumentRow(*row) for row in rows]


def _one(found: list[DocumentRow], elem_id: int | None = None) -> Resolved | None:
    if len(found) == 1:
        return Resolved(found[0], [], elem_id)
    if found:
        return Resolved(None, found)
    return None


NAME_MIN = 0.6  # word_similarity of the query inside the title
NAME_MARGIN = 0.1  # the best match must beat the next one by this much
CANDIDATE_MIN = 0.3  # weaker matches are not even offered as candidates


def resolve_document(conn: psycopg.Connection, ref: str | int) -> Resolved:
    """Document by id, lex.uz URL, number, abbreviation or (fuzzy) name."""
    text = str(ref).strip()
    if match := _URL_RE.search(text):
        lex_id = -abs(int(match[1]))
        elem = int(match[2]) if match[2] else None
        return _one(fetch_documents(conn, "id = %s", [lex_id]), elem) or Resolved(None, [])
    if match := _ID_RE.match(text):
        lex_id = -abs(int(match[1]))
        if found := _one(fetch_documents(conn, "id = %s", [lex_id])):
            return found
    number = key(text)
    if number and any(c.isdigit() for c in number):
        found = fetch_documents(
            conn,
            NUMBER_MATCH,
            [number],
            "ORDER BY (status = 'in_force') DESC, adopted_at DESC NULLS LAST",
        )
        in_force = [d for d in found if d.in_force]
        if len(in_force) == 1:  # old acts that lost force often share the number
            return Resolved(in_force[0], [])
        if resolved := _one(found):
            return resolved
    abbr = abbreviation(text)
    if abbr:
        found = fetch_documents(
            conn,
            "display_title ILIKE %s AND doc_kind IN ('kodeks', 'konstitutsiya')",
            [abbr + "%"],
            "ORDER BY display_title",
        )
        if resolved := _one(found):
            return resolved
    if looks_like_number(text):
        return Resolved(None, [])  # a fuzzy title match for "PF-60" would be a wrong act
    return resolve_by_name(conn, text)


def resolve_by_name(
    conn: psycopg.Connection,
    text: str,
    where: str = "TRUE",
    params: Sequence = (),
    limit: int = 5,
) -> Resolved:
    """Fuzzy title match; one document only when it clearly beats the others."""
    query = fold(text)
    if len(query) < 3:
        return Resolved(None, [])
    with conn.transaction():
        conn.execute(f"SET LOCAL pg_trgm.word_similarity_threshold = {CANDIDATE_MIN}")
        rows = conn.execute(
            f"""
            SELECT {DOC_COLUMNS}, word_similarity(%s, title_norm) AS ws
            FROM documents
            WHERE %s <%% title_norm AND {where}
            ORDER BY ws DESC, (status = 'in_force') DESC, similarity(%s, title_norm) DESC
            LIMIT {int(limit)}
            """,
            [query, query, *params, query],
        ).fetchall()
    found = [(DocumentRow(*row[:-1]), row[-1]) for row in rows]
    if not found:
        return Resolved(None, [])
    best, score = found[0]
    runner_up = found[1][1] if len(found) > 1 else 0.0
    if score >= NAME_MIN and score - runner_up >= NAME_MARGIN:
        return Resolved(best, [])
    # Several equally good names ("Fuqarolik kodeksi" has two parts): let the client choose,
    # but do not offer titles that only share a word or two.
    return Resolved(None, [d for d, s in found if s >= score - NAME_MARGIN * 1.5])


_SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
_UNIT_WORDS = re.compile(r"(?i)\s*-?\s*(modda|moddasi|band|bandi|статья|ст\.?|пункт|п\.)\s*")


def normalize_unit_number(text: str) -> str:
    """Unit number: "161-modda", "161", "10¹", "10-1", "10^1", "ст. 10¹" → "161" / "10¹"."""
    value = _UNIT_WORDS.sub(" ", str(text)).strip().strip(".")
    match = re.fullmatch(r"(\d+)\s*(?:[-^]\s*(\d+)|([⁰¹²³⁴⁵⁶⁷⁸⁹]+))?", value)
    if not match:
        return value
    base, sup_digits, sup = match[1], match[2], match[3]
    if sup_digits:
        return base + to_superscript(sup_digits)
    if sup:
        return base + to_superscript(sup.translate(_SUPERSCRIPT))
    return base


def unit_kinds(doc_kind: str) -> tuple[str, ...]:
    """Which unit kinds an "article" reference means, in order of preference."""
    if doc_kind in ("konstitutsiya", "kodeks", "qonun"):
        return ("modda", "band")
    return ("band", "modda")
