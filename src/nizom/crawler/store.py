"""Raw page storage: ``data/raw/{docs,cards}/{id}.html.gz`` plus ``.meta.json``."""

import gzip
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

Kind = Literal["docs", "cards"]


class RawStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, kind: Kind, lex_id: int) -> Path:
        return self.root / kind / f"{lex_id}.html.gz"

    def meta_path(self, kind: Kind, lex_id: int) -> Path:
        return self.root / kind / f"{lex_id}.meta.json"

    def has(self, kind: Kind, lex_id: int) -> bool:
        return self.path(kind, lex_id).exists()

    def save(self, kind: Kind, lex_id: int, text: str, url: str, status: int) -> dict:
        data = text.encode("utf-8")
        target = self.path(kind, lex_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_bytes(gzip.compress(data))
        tmp.replace(target)
        meta = {
            "url": url,
            "status": status,
            "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        }
        self.meta_path(kind, lex_id).write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return meta

    def load(self, kind: Kind, lex_id: int) -> str:
        return gzip.decompress(self.path(kind, lex_id).read_bytes()).decode("utf-8")

    def meta(self, kind: Kind, lex_id: int) -> dict:
        return json.loads(self.meta_path(kind, lex_id).read_text(encoding="utf-8"))
