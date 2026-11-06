"""Write parsed documents into PostgreSQL: documents → sections → chunks (+ FTS, embeddings)."""

import hashlib
import json
import logging
from dataclasses import dataclass, field

import numpy as np
import psycopg
from psycopg.types.json import Jsonb

from qonunshunos.index.doctype import display_title, doc_kind
from qonunshunos.index.embed import Embed
from qonunshunos.parser.card import DocumentCard
from qonunshunos.parser.models import Heading, ParsedDocument, Unit
from qonunshunos.text.chunk import Chunk, chunk_unit, unit_text
from qonunshunos.text.fts import to_fts_text
from qonunshunos.text.normalize import fold

log = logging.getLogger(__name__)

# Bumped when the writer changes what it stores (headings, kinds), so documents are rewritten.
INDEX_VERSION = 2


def kind_and_title(document: ParsedDocument, card: DocumentCard | None) -> tuple[str, str]:
    """Normalized kind and the display title used in tool output and chunk headings."""
    bodies = " ".join(
        [document.accepting_body or "", *(b.organ or "" for b in (card.bodies if card else []))]
    )
    form = card.form if card else None
    if form is None and "kodeks" in document.title.lower():
        form = "kodeks"
    if form is None and "konstitutsiya" in document.title.lower():
        form = "konstitutsiya"
    kind = doc_kind(form, document.number, bodies)
    return kind, display_title(document.title, kind, document.number)


def content_hash(document: ParsedDocument, card: DocumentCard | None) -> str:
    payload = {
        "index_version": INDEX_VERSION,
        "document": document.model_dump(mode="json"),
        "card": card.model_dump(mode="json") if card else None,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass
class SectionRow:
    kind: str
    number: str | None
    title: str | None
    path: list[str]
    elem_id: int | None
    text: str
    level: int | None = None
    extra: dict = field(default_factory=dict)
    unit: Unit | None = None


def build_sections(document: ParsedDocument) -> list[SectionRow]:
    """Interleave headings and units in reading order.

    Units carry the path of headings they live under; a heading is emitted when it first
    appears in a unit's path (or differs from the previous unit's path at its level).
    Heading metadata is looked up forward in ``document.headings`` by text.
    """
    rows: list[SectionRow] = []
    headings = document.headings
    cursor = 0
    previous: list[str] = []

    def find_heading(text: str) -> Heading | None:
        nonlocal cursor
        for i in range(cursor, len(headings)):
            if headings[i].text == text:
                cursor = i + 1
                return headings[i]
        return None

    for unit in document.units:
        common = 0
        while common < min(len(previous), len(unit.path)) and previous[common] == unit.path[common]:
            common += 1
        for depth in range(common, len(unit.path)):
            text = unit.path[depth]
            heading = find_heading(text)
            rows.append(
                SectionRow(
                    kind=heading.kind if heading else "sarlavha",
                    number=heading.number if heading else None,
                    title=heading.title if heading else text,
                    path=unit.path[:depth],
                    elem_id=heading.elem_id if heading else None,
                    text=text,
                    level=heading.level if heading else None,
                )
            )
        previous = unit.path
        extra = {}
        if unit.okoz:
            extra["okoz"] = unit.okoz
        if unit.changes:
            extra["changes"] = [c.model_dump(mode="json") for c in unit.changes]
        if unit.comments:
            extra["comments"] = [c.model_dump(mode="json") for c in unit.comments]
        rows.append(
            SectionRow(
                kind=unit.kind,
                number=unit.number,
                title=unit.title,
                path=unit.path,
                elem_id=unit.elem_id,
                text=unit_text(unit),
                extra=extra,
                unit=unit,
            )
        )
    return rows


def _date(value: str | None) -> str | None:
    return value or None


def stored_hash(conn: psycopg.Connection, lex_id: int) -> str | None:
    row = conn.execute("SELECT content_hash FROM documents WHERE id = %s", (lex_id,)).fetchone()
    return row[0] if row else None


def index_document(
    conn: psycopg.Connection,
    document: ParsedDocument,
    card: DocumentCard | None,
    embedder: Embed,
    *,
    use_stem: bool = True,
    force: bool = False,
) -> int | None:
    """(Re)write one document. Returns the number of chunks, or ``None`` if unchanged."""
    digest = content_hash(document, card)
    if not force and stored_hash(conn, document.lex_id) == digest:
        return None

    status = card.status if card else "unknown"
    kind, name = kind_and_title(document, card)
    searchable = status == "in_force" and document.content == "html"
    sections = build_sections(document) if searchable else []
    chunks: list[tuple[int, Chunk]] = []
    for index, row in enumerate(sections):
        if row.unit is not None:
            chunks.extend((index, c) for c in chunk_unit(name, row.unit))
    vectors = (
        embedder.passages([c.passage for _, c in chunks])
        if chunks
        else np.zeros((0, 384), dtype=np.float32)
    )

    meta = {
        "alternates": document.alternates,
        "okoz": document.okoz,
        "tsz": document.tsz,
        "signature": document.signature,
        "signed_place": document.signed_place,
        "signed_date": document.signed_date,
        "publication_origin": document.publication_origin,
        "notes": document.notes,
        "parser_version": document.parser_version,
        "embed_model": getattr(embedder, "name", "unknown"),
        "fts_stem": use_stem,
    }
    title_norm = fold(" ".join(p for p in (document.title, document.number or "") if p))

    with conn.transaction():
        conn.execute("DELETE FROM documents WHERE id = %s", (document.lex_id,))
        conn.execute(
            """
            INSERT INTO documents (id, title, display_title, doc_type, doc_kind, number,
                adopted_at, status,
                accepting_body, url, content, edition_date, last_change_date, content_hash,
                card, meta, title_norm)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                document.lex_id,
                document.title,
                name,
                card.form if card else None,
                kind,
                document.number,
                _date(document.date),
                status,
                document.accepting_body,
                document.url,
                document.content,
                _date(document.edition_date),
                _date(document.last_change_date),
                digest,
                Jsonb(card.model_dump(mode="json")) if card else None,
                Jsonb(meta),
                title_norm,
            ),
        )
        section_ids: list[int] = []
        with conn.cursor() as cur:
            for ord_, row in enumerate(sections):
                cur.execute(
                    """
                    INSERT INTO sections (document_id, ord, kind, level, number, title, path,
                        elem_id, text, extra)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                    """,
                    (
                        document.lex_id,
                        ord_,
                        row.kind,
                        row.level,
                        row.number,
                        row.title,
                        row.path,
                        row.elem_id,
                        row.text,
                        Jsonb(row.extra),
                    ),
                )
                section_ids.append(cur.fetchone()[0])
            cur.executemany(
                """
                INSERT INTO chunks (document_id, section_id, ord, heading, text, tsv, embedding)
                VALUES (%s, %s, %s, %s, %s,
                    setweight(to_tsvector('simple', %s), 'A')
                    || setweight(to_tsvector('simple', %s), 'B'),
                    %s::halfvec)
                """,
                [
                    (
                        document.lex_id,
                        section_ids[index],
                        ord_,
                        chunk.heading,
                        chunk.text,
                        to_fts_text(chunk.heading, use_stem),
                        to_fts_text(chunk.text, use_stem),
                        vectors[ord_].tolist(),
                    )
                    for ord_, (index, chunk) in enumerate(chunks)
                ],
            )
    log.info("indexed %s: %d sections, %d chunks", document.lex_id, len(sections), len(chunks))
    return len(chunks)


def rebuild_fts(conn: psycopg.Connection, use_stem: bool) -> int:
    """Recompute ``chunks.tsv`` (e.g. after changing the stemmer) without re-embedding."""
    rows = conn.execute("SELECT id, heading, text FROM chunks").fetchall()
    with conn.transaction(), conn.cursor() as cur:
        cur.executemany(
            "UPDATE chunks SET tsv = setweight(to_tsvector('simple', %s), 'A')"
            " || setweight(to_tsvector('simple', %s), 'B') WHERE id = %s",
            [(to_fts_text(h, use_stem), to_fts_text(t, use_stem), i) for i, h, t in rows],
        )
        cur.execute("UPDATE documents SET meta = meta || %s", (Jsonb({"fts_stem": use_stem}),))
    refresh_fts_stats(conn)
    return len(rows)


def refresh_fts_stats(conn: psycopg.Connection) -> int:
    """Recount document frequencies of FTS terms (``ts_stat`` over all chunks)."""
    with conn.transaction():
        conn.execute("TRUNCATE fts_stats")
        conn.execute(
            "INSERT INTO fts_stats (word, ndoc)"
            " SELECT word, ndoc FROM ts_stat('SELECT tsv FROM chunks')"
        )
    return conn.execute("SELECT count(*) FROM fts_stats").fetchone()[0]
