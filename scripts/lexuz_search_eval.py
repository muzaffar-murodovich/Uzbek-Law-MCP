"""Measure lex.uz's "Matndagi so'z yoki jumla" text filter on 208 LLM questions (6m).

lex.uz returns acts, not articles, so a hit is "an expected act among the first 10 results".

    uv run python scripts/lexuz_search_eval.py build > /tmp/lexuz_remote.py
    ssh myserver 'cd /home/deploy/qonunshunos && venv/bin/python -' < /tmp/lexuz_remote.py \
        > eval/results/2026-11-24-lexuz-search.jsonl
    uv run python scripts/lexuz_search_eval.py report eval/results/2026-11-24-lexuz-search.jsonl

The remote script embeds the queries, so the server needs no eval files. It sends one request per
query variant (4 × 208) through ``LexClient`` with 2.5 s between requests.
"""

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "eval" / "questions_llm_full.yaml"
ALT = ROOT / "eval" / "alt_llm_questions_llm_full.json"
KINDS = ("question", "alt", "kw2", "kw3")

REMOTE = """
import json
from urllib.parse import quote
from nizom.crawler.client import LexClient
from nizom.crawler.listing import parse_listing
ITEMS = json.loads(%s)
with LexClient(min_interval=2.5) as c:
    for it in ITEMS:
        out = {"id": it["id"], "docs": it["docs"]}
        for kind in %r:
            try:
                p = c.request("GET", "/uz/search/nat?lang=4&status=Y&query=" + quote(it[kind]))
                lp = parse_listing(p.text)
                out[kind] = {"total": lp.total, "ids": [r.lex_id for r in lp.rows[:10]]}
            except Exception as e:
                out[kind] = {"error": str(e)}
        print(json.dumps(out), flush=True)
"""


def lexuz_spelling(text: str) -> str:
    """o' g' → oʻ gʻ, other apostrophes → ʼ (the spelling lex.uz uses)."""
    text = re.sub(r"([oOgG])['‘’`ʼ]", lambda m: m.group(1) + "ʻ", text)
    return re.sub(r"['‘’`]", "ʼ", text)


def cut(text: str, limit: int = 100) -> str:
    """Drop punctuation and cut to lex.uz's 100-character limit at a word boundary."""
    text = " ".join(re.sub(r"[?!.,;:]", " ", text).split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0]


def items() -> list[dict]:
    alt = json.loads(ALT.read_text())
    out = []
    for q in yaml.safe_load(QUESTIONS.read_text()):
        if "aniq" not in q["tags"]:
            continue
        phrase = cut(lexuz_spelling(alt[q["id"]][0]))
        out.append(
            {
                "id": q["id"],
                "docs": sorted({e["document"] for e in q["expected"]}),
                "question": cut(lexuz_spelling(q["question"])),
                "alt": phrase,
                "kw2": " ".join(phrase.split()[:2]),
                "kw3": " ".join(phrase.split()[:3]),
            }
        )
    return out


def report(path: str) -> None:
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line]
    for kind in KINDS:
        have = [r for r in rows if kind in r]
        if not have:
            continue
        found = sum(bool(r[kind].get("ids")) for r in have)
        hit10 = sum(any(i in r["docs"] for i in r[kind].get("ids", [])) for r in have)
        hit1 = sum(bool(r[kind].get("ids")) and r[kind]["ids"][0] in r["docs"] for r in have)
        n = len(have)
        print(
            f"{kind:8} n={n} any result {found / n:.3f}  R@1 {hit1 / n:.3f}  R@10 {hit10 / n:.3f}"
        )


if __name__ == "__main__":
    if sys.argv[1:2] == ["build"]:
        print(REMOTE % (repr(json.dumps(items(), ensure_ascii=False)), KINDS))
    elif sys.argv[1:2] == ["report"]:
        report(sys.argv[2])
    else:
        sys.exit(__doc__)
