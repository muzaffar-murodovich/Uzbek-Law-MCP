"""Summarize scripts/e2e_claude.sh transcripts: tools used, expected article read, links.

    uv run python scripts/e2e_analyze.py data/e2e > eval/results/<date>-e2e.jsonl

A link counts as bad when it points to a document or element that is not in the database
(links copied from "LexUZ sharhi" to acts outside the corpus also land here).
"""

import json
import re
import sys
from pathlib import Path

import psycopg
import yaml

from qonunshunos.config import Settings, load_dotenv
from qonunshunos.mcp.resolve import normalize_unit_number, resolve_document

D = Path(sys.argv[1])
load_dotenv()
conn = psycopg.connect(Settings.from_env().dsn, autocommit=True)
qs = {q["id"]: q for q in yaml.safe_load(Path("eval/questions.yaml").read_text(encoding="utf-8"))}
DISCLAIMER = re.compile(r"yuridik maslahat emas|не является юридической|не юридическ", re.I)
URL = re.compile(r"https://lex\.uz/docs/(-?\d+)(?:#(-?\d+))?")
rows = []
for f in sorted(D.glob("runs/*.jsonl")):
    rid = f.stem
    calls, text, result = [], "", {}
    for line in f.read_text().splitlines():
        e = json.loads(line)
        if e.get("type") == "assistant":
            for c in e["message"]["content"]:
                if c["type"] == "tool_use":
                    calls.append((c["name"].split("__")[-1], c["input"]))
                elif c["type"] == "text":
                    text += c["text"] + "\n"
        elif e.get("type") == "result":
            result = e
            text = e.get("result") or text
    searches = [a for n, a in calls if n == "search_law"]
    read = set()
    for n, a in calls:
        if n == "get_article":
            r = resolve_document(conn, a["document"])
            if r.document:
                read.add((r.document.id, normalize_unit_number(a["article"])))
    expected = qs.get(rid.removesuffix("-ru"), {}).get("expected", [])
    hit = any((e["document"], e["article"]) in read for e in expected)
    urls = URL.findall(text)
    bad = []
    for doc, elem in urls:
        if elem:
            ok = conn.execute(
                "SELECT 1 FROM sections WHERE document_id=%s AND elem_id=%s", (int(doc), int(elem))
            ).fetchone()
        else:
            ok = conn.execute("SELECT 1 FROM documents WHERE id=%s", (int(doc),)).fetchone()
        if not ok:
            bad.append(f"{doc}#{elem}")
    rows.append(
        dict(
            id=rid,
            tools=" ".join(n for n, _ in calls),
            searches=len(searches),
            alt=all(s.get("alt_queries") for s in searches) if searches else False,
            read=sorted(f"{d}:{a}" for d, a in read),
            expected=[f"{e['document']}:{e['article']}" for e in expected],
            hit=hit,
            links=len(urls),
            bad_links=bad,
            disclaimer=bool(DISCLAIMER.search(text)),
            turns=result.get("num_turns"),
            secs=round((result.get("duration_ms") or 0) / 1000),
            cost=round(result.get("total_cost_usd") or 0, 3),
        )
    )
for r in rows:
    print(json.dumps(r, ensure_ascii=False))
print(
    "SUMMARY",
    json.dumps(
        {
            "n": len(rows),
            "alt": sum(r["alt"] for r in rows),
            "hit": sum(r["hit"] for r in rows),
            "bad_links": sum(len(r["bad_links"]) for r in rows),
            "disclaimer": sum(r["disclaimer"] for r in rows),
            "cost": round(sum(r["cost"] for r in rows), 2),
        }
    ),
)
