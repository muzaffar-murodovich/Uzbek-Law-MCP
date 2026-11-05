"""Split parsed units into search chunks.

A unit (modda, band, ...) that fits is one chunk. A longer one is cut at paragraph
boundaries; its lead paragraph ("Quyidagilar ...:") is repeated in every piece because the
enumerated items that follow make no sense without it.
"""

import re
from dataclasses import dataclass

from qonunshunos.parser.models import Unit

SINGLE_MAX = 1500  # chars; e5 truncates at 512 tokens ≈ 2300 chars of Uzbek Latin
PIECE_TARGET = 1100
LEAD_MAX = 450
MAX_PIECES = 30

_SENTENCE_RE = re.compile(r"(?<=[.;:!?])\s+")


@dataclass
class Chunk:
    heading: str  # context line: document, path, unit label
    text: str  # the piece shown to users

    @property
    def passage(self) -> str:
        """Text given to the embedding model."""
        return f"{self.heading}\n{self.text}"


def unit_label(unit: Unit) -> str:
    number = unit.number or ""
    if unit.kind == "modda":
        label = f"{number}-modda"
    elif unit.kind == "band":
        label = f"{number}-band"
    elif unit.kind == "kirish":
        label = "Kirish qismi"
    else:
        label = ""
    if unit.title:
        label = f"{label}. {unit.title}" if label else unit.title
    return label


def unit_text(unit: Unit) -> str:
    """Paragraphs and table rows of a unit, one per line."""
    lines = [p.text for p in unit.paragraphs if p.text]
    for table in unit.tables:
        lines.extend(" | ".join(cell for cell in row if cell) for row in table.rows)
    return "\n".join(line for line in lines if line.strip())


def heading_for(short_title: str, unit: Unit) -> str:
    parts = [short_title, *unit.path[-2:], unit_label(unit)]
    return ". ".join(p.strip().rstrip(".") for p in parts if p and p.strip())


def _split_long(line: str) -> list[str]:
    """Cut one over-long paragraph at sentence boundaries (hard cut as a last resort)."""
    pieces, current = [], ""
    for sentence in _SENTENCE_RE.split(line):
        while len(sentence) > PIECE_TARGET:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence[:PIECE_TARGET])
            sentence = sentence[PIECE_TARGET:]
        if current and len(current) + 1 + len(sentence) > PIECE_TARGET:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence
    if current:
        pieces.append(current)
    return pieces


def split_text(text: str) -> list[str]:
    if len(text) <= SINGLE_MAX:
        return [text] if text else []
    lines = text.split("\n")
    lead = ""
    for i, line in enumerate(lines[:3]):
        if line.rstrip().endswith(":"):
            candidate = "\n".join(lines[: i + 1])
            if len(candidate) <= LEAD_MAX:
                lead, lines = candidate, lines[i + 1 :]
            break
    budget = PIECE_TARGET - len(lead)
    pieces: list[str] = []
    current: list[str] = []
    size = 0
    for line in lines:
        for part in _split_long(line) if len(line) > budget else [line]:
            if current and size + len(part) + 1 > budget:
                pieces.append("\n".join(current))
                current, size = [], 0
            current.append(part)
            size += len(part) + 1
    if current:
        pieces.append("\n".join(current))
    if lead:
        pieces = [f"{lead}\n{p}" for p in pieces]
    return pieces[:MAX_PIECES]


def chunk_unit(short_title: str, unit: Unit) -> list[Chunk]:
    heading = heading_for(short_title, unit)
    pieces = split_text(unit_text(unit))
    if not pieces and unit.title:
        pieces = [unit.title]  # e.g. "Chiqarib tashlangan" articles carry only a heading
    return [Chunk(heading=heading, text=p) for p in pieces]
