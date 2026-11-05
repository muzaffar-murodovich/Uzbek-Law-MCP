"""Fetch → store → parse steps shared by the CLI commands."""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from qonunshunos.crawler.client import LexClient, card_path, document_path
from qonunshunos.crawler.listing import CODES_LISTING, iter_listing
from qonunshunos.crawler.store import RawStore
from qonunshunos.parser.card import DocumentCard, parse_card
from qonunshunos.parser.document import ParsedDocument, parse_document

log = logging.getLogger(__name__)

CONSTITUTION_ID = -6445145


@dataclass
class Workspace:
    data_dir: Path

    @property
    def raw(self) -> RawStore:
        return RawStore(self.data_dir / "raw")

    def parsed_path(self, lex_id: int) -> Path:
        return self.data_dir / "parsed" / f"{lex_id}.json"


def fetch(client: LexClient, ws: Workspace, lex_id: int, force: bool = False) -> None:
    """Download the document page and its card unless they are already stored."""
    raw = ws.raw
    for kind, path in (("docs", document_path(lex_id)), ("cards", card_path(lex_id))):
        if raw.has(kind, lex_id) and not force:
            continue
        page = client.get(path)
        raw.save(kind, lex_id, page.text, page.url, page.status)
        log.info("fetched %s %s", kind, lex_id)


def parse(ws: Workspace, lex_id: int) -> tuple[ParsedDocument, DocumentCard | None]:
    raw = ws.raw
    doc_url = raw.meta("docs", lex_id)["url"]
    document = parse_document(raw.load("docs", lex_id), lex_id, url=doc_url)
    card = parse_card(raw.load("cards", lex_id), lex_id) if raw.has("cards", lex_id) else None
    target = ws.parsed_path(lex_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "document": document.model_dump(mode="json"),
        "card": card.model_dump(mode="json") if card else None,
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return document, card


def sample_ids(client: LexClient) -> list[int]:
    """Constitution plus every code in force (Latin versions)."""
    codes = [row.lex_id for row in iter_listing(client, CODES_LISTING) if row.in_force]
    return [CONSTITUTION_ID, *codes]


def load_parsed(ws: Workspace, lex_id: int) -> tuple[ParsedDocument, DocumentCard | None]:
    payload = json.loads(ws.parsed_path(lex_id).read_text(encoding="utf-8"))
    card = payload.get("card")
    return ParsedDocument(**payload["document"]), DocumentCard(**card) if card else None


def parsed_ids(ws: Workspace) -> list[int]:
    folder = ws.data_dir / "parsed"
    return sorted(int(p.stem) for p in folder.glob("*.json")) if folder.is_dir() else []
