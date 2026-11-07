"""Parsed representations of lex.uz pages."""

from typing import Literal

from pydantic import BaseModel, Field

PARSER_VERSION = "1"

UnitKind = Literal["modda", "band", "kirish", "matn"]
HeadingKind = Literal["ilova", "qism", "boʻlim", "bob", "paragraf", "sarlavha"]


class Link(BaseModel):
    doc_id: int
    elem_id: int | None = None
    ondate: str | None = None  # ISO date of the linked edition
    text: str = ""


class Paragraph(BaseModel):
    elem_id: int | None
    text: str
    links: list[Link] = Field(default_factory=list)


class Change(BaseModel):
    """``CHANGES_ORIGINS``: which act changed the preceding text."""

    elem_id: int | None
    text: str
    links: list[Link] = Field(default_factory=list)


class Comment(BaseModel):
    """LexUZ sharhi: editorial comment, not normative text."""

    elem_id: int | None
    text: str
    links: list[Link] = Field(default_factory=list)


class PendingChange(BaseModel):
    """lex.uz banner "Hujjatga o'zgartirish kiritilmoqda": an amendment not yet in the text."""

    text: str  # "Hujjatga oʻzgartirish kiritilmoqda. Asos: … 02.11.2026 yildagi OʻRQ-1186-son"
    basis: list[Link] = Field(default_factory=list)


class Table(BaseModel):
    elem_id: int | None
    rows: list[list[str]]


class Heading(BaseModel):
    elem_id: int | None
    level: int  # 0 ilova, 1 qism, 2 boʻlim, 3 bob, 4 paragraf, 5 other
    kind: HeadingKind
    number: str | None
    title: str
    text: str


class Unit(BaseModel):
    kind: UnitKind
    number: str | None = None  # "161", "126¹"
    title: str | None = None
    elem_id: int | None = None
    path: list[str] = Field(default_factory=list)
    paragraphs: list[Paragraph] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    changes: list[Change] = Field(default_factory=list)
    comments: list[Comment] = Field(default_factory=list)
    okoz: list[str] = Field(default_factory=list)


class ParsedDocument(BaseModel):
    lex_id: int
    lang: str = "uz-Latn"
    url: str
    content: Literal["html", "pdf_only"]
    title: str
    number: str | None = None  # "OʻRQ-42", "PF-60", "606"
    date: str | None = None  # ISO adoption date from <title>
    edition_date: str | None = None  # ISO date of the current edition (not on every page)
    last_change_date: str | None = None  # latest ONDATE among CHANGES_ORIGINS links
    alternates: dict[str, int] = Field(default_factory=dict)
    accepting_body: str | None = None
    signature: str | None = None
    signed_place: str | None = None
    signed_date: str | None = None
    signed_number: str | None = None
    okoz: list[str] = Field(default_factory=list)
    tsz: list[str] = Field(default_factory=list)
    publication_origin: str | None = None
    notes: list[str] = Field(default_factory=list)
    changes: list[Change] = Field(default_factory=list)  # not attached to any unit
    comments: list[Comment] = Field(default_factory=list)  # not attached to any unit
    headings: list[Heading] = Field(default_factory=list)
    units: list[Unit] = Field(default_factory=list)
    pending_changes: list[PendingChange] = Field(default_factory=list)  # lx_strip banners
    warnings: list[str] = Field(default_factory=list)
    parser_version: str = PARSER_VERSION
