"""lex.uz RSS feed (``/uz/rss``): acts published during the last month, newest first."""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from qonunshunos.parser.common import dmy_to_iso
from qonunshunos.text.normalize import normalize_text

RSS_PATH = "/uz/rss"

_ID_RE = re.compile(r"/docs/(-?\d+)")
_ADOPTED_RE = re.compile(r"Qabul qilingan sana (\d{2}\.\d{2}\.\d{4})")
_IN_FORCE_RE = re.compile(r"Kuchga kirish sanasi (\d{2}\.\d{2}\.\d{4})")


@dataclass
class RssItem:
    lex_id: int  # negative for Latin pages; positive ids are other language versions
    title: str
    info: str  # "Oʻzbekiston Respublikasining Qonuni №O‘RQ-1186. Qabul qilingan sana …"
    adopted: str | None  # ISO
    in_force: str | None  # ISO; may lie in the future


def parse_rss(xml: str) -> list[RssItem]:
    root = ET.fromstring(xml.lstrip("﻿"))
    items = []
    for item in root.iter("item"):
        m = _ID_RE.search(item.findtext("link") or item.findtext("guid") or "")
        if m is None:
            continue
        info = normalize_text(item.findtext("description") or "")
        adopted = _ADOPTED_RE.search(info)
        in_force = _IN_FORCE_RE.search(info)
        items.append(
            RssItem(
                lex_id=int(m.group(1)),
                title=normalize_text(item.findtext("title") or ""),
                info=info,
                adopted=dmy_to_iso(adopted.group(1)) if adopted else None,
                in_force=dmy_to_iso(in_force.group(1)) if in_force else None,
            )
        )
    return items
