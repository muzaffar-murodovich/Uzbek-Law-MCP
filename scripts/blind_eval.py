"""Evaluation questions written without seeing the law, labelled without our search.

``questions_llm_full`` is written from one article each and labelled partly by judging what our
own search found, so it favours our search. Here a model (Claude subagents) writes questions
from life situations only; another one finds the answering articles by reading the corpus with
``grep``/``show`` below, which never touch the search index (docs/stage2-experiments.md 6k).

    uv run python scripts/blind_eval.py units          # on home: data/parsed -> units file
    uv run python scripts/blind_eval.py grep 'mehnat ta.til' --title 'Mehnat kodeksi'
    uv run python scripts/blind_eval.py show -- -6257288 134
    uv run python scripts/blind_eval.py build data/eval/blind/labels/*.json \
        --judged data/eval/blind/judged.json
"""

import argparse
import gzip
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path

import yaml

UNITS = Path("data/eval/blind/units.tsv.gz")
COLUMNS = ("document", "doc_kind", "title", "kind", "number", "path", "text")
APOSTROPHES = "ʻʼ‘’'`"


def export_units(args: argparse.Namespace) -> None:
    """One line per unit of every current Latin document, as the index stores them."""
    from qonunshunos.crawler.pipeline import Workspace, load_parsed
    from qonunshunos.index.writer import build_sections, kind_and_title

    ws = Workspace(args.data_dir)
    files = sorted((args.data_dir / "parsed").glob("*.json"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with gzip.open(args.out, "wt", encoding="utf-8") as out:
        for n, path in enumerate(files, start=1):
            document, card = load_parsed(ws, int(path.stem))
            if card is not None and card.status != "in_force":
                continue
            kind, title = kind_and_title(document, card)
            for row in build_sections(document):
                if row.unit is None:  # headings: their text is in the units' path
                    continue
                fields = [
                    str(document.lex_id),
                    kind,
                    title,
                    row.kind,
                    row.number or "",
                    " > ".join(row.path),
                    f"[{row.title}] {row.text}" if row.title else row.text,
                ]
                out.write("\t".join(clean(f) for f in fields) + "\n")
                count += 1
            if n % 2000 == 0:
                print(f"{n}/{len(files)} documents, {count} units", file=sys.stderr, flush=True)
    print(f"{count} units from {len(files)} documents -> {args.out}")


def clean(text: str) -> str:
    return text.replace("\t", " ").replace("\r", " ").replace("\n", " ¶ ")


def units() -> Iterator[dict]:
    with gzip.open(UNITS, "rt", encoding="utf-8") as f:
        for line in f:
            yield dict(zip(COLUMNS, line.rstrip("\n").split("\t"), strict=True))


def pattern(text: str) -> re.Pattern:
    """Case-insensitive regex; any apostrophe in it matches every apostrophe form."""
    # One pass: replacing character by character would also rewrite the classes already put in.
    text = re.sub(f"[{APOSTROPHES}]", f"[{APOSTROPHES}]", text)
    return re.compile(text, re.IGNORECASE)


def grep(args: argparse.Namespace) -> None:
    text_re = [pattern(p) for p in args.patterns]
    title_re = pattern(args.title) if args.title else None
    kinds = set(args.kind.split(",")) if args.kind else None
    shown, matched_docs = 0, {}
    for u in units():
        if args.doc and u["document"] != args.doc:
            continue
        if kinds and u["doc_kind"] not in kinds:
            continue
        if title_re and not title_re.search(u["title"]):
            continue
        hay = f"{u['path']} {u['text']}"
        found = [r.search(hay) for r in text_re]
        if not all(found):
            continue
        matched_docs[u["document"]] = matched_docs.get(u["document"], 0) + 1
        if shown < args.limit and matched_docs[u["document"]] <= args.per_doc:
            start = max(found[0].start() - args.context, 0)
            snippet = hay[start : found[0].end() + args.context]
            print(f"{u['document']} | {u['kind']} {u['number']} | {u['title'][:90]}")
            print(f"    path: {u['path'][:160]}")
            print(f"    …{snippet}…")
            shown += 1
    print(f"-- {sum(matched_docs.values())} units in {len(matched_docs)} documents matched")


def titles(args: argparse.Namespace) -> None:
    title_re = pattern(args.pattern)
    seen = set()
    for u in units():
        if u["document"] in seen or not title_re.search(u["title"]):
            continue
        seen.add(u["document"])
        print(f"{u['document']} | {u['doc_kind']} | {u['title'][:150]}")
        if len(seen) >= args.limit:
            break
    print(f"-- {len(seen)} documents shown")


def show(args: argparse.Namespace) -> None:
    """A unit's full text, or a document's table of contents."""
    within = pattern(args.within) if args.within else None
    for u in units():
        if u["document"] != args.document:
            continue
        if args.number is None:
            print(f"{u['kind']} {u['number']} | {u['path'][-80:]} | {u['text'][:100]}")
        elif u["number"] == args.number and (within is None or within.search(u["path"])):
            print(f"{u['title']}\n{u['kind']} {u['number']}\npath: {u['path']}\n")
            print(u["text"].replace(" ¶ ", "\n"))
            print()


def build(args: argparse.Namespace) -> None:
    """Questions YAML from the labellers' JSON files; checks every label against the units."""
    known: dict[tuple[str, str], list[str]] = {}
    for u in units():
        known.setdefault((u["document"], u["number"]), []).append(u["path"])
    trained = set()
    if args.pairs and args.pairs.exists():
        for line in args.pairs.read_text(encoding="utf-8").splitlines():
            pair = json.loads(line)
            trained.add((str(pair["document_id"]), str(pair["number"])))
    # Units our search found for questions it missed, accepted by a judge (pooled relevance):
    # they carry ``judged: true`` so the strict number can still be computed without them.
    judged = json.loads(args.judged.read_text(encoding="utf-8")) if args.judged else {}
    items, dropped = [], []
    for path in args.labels:
        for entry in json.loads(path.read_text(encoding="utf-8")):
            expected = []
            answers = [*entry.get("answers", [])]
            answers += [{**a, "judged": True} for a in judged.get(entry["id"], [])]
            for a in answers:
                # "matn": an unnumbered unit (annex table); its number is empty in the index.
                number = "" if str(a["article"]) == "matn" else str(a["article"])
                key = (str(a["document"]), number)
                paths = known.get(key, [])
                within = a.get("within") or ""
                if not any(within in p for p in paths):
                    dropped.append(f"{entry['id']}: no unit {key} within {within!r}")
                    continue
                e = {"document": int(key[0]), "article": key[1]}
                # The number repeats in this document: pin the path. An empty ``within`` means
                # the decree's own clause only when one of them has an empty path.
                if len(paths) > 1 and (within or "" in paths):
                    e["within"] = within
                    hits = [p for p in paths if (within in p if within else not p)]
                    if len(hits) > 1:
                        print(f"warning {entry['id']}: within {within!r} fits {len(hits)} units")
                elif len(paths) > 1:
                    print(f"warning {entry['id']}: {key} repeats, no within: any of them counts")
                if a.get("judged"):
                    e["judged"] = True
                expected.append(e)
            if not expected:
                dropped.append(f"{entry['id']}: no answer ({entry.get('note', '')})")
                continue
            tags = ["blind", entry.get("domain", "boshqa")]
            if any((str(e["document"]), e["article"]) in trained for e in expected):
                tags.append("trained")  # an answer was a positive of the fine-tune pairs
            items.append(
                {
                    "id": entry["id"],
                    "question": entry["question"],
                    "expected": expected,
                    "tags": tags,
                    "note": entry.get("note", ""),
                }
            )
    items.sort(key=lambda i: i["id"])
    header = (
        "# Written by Claude subagents from life situations, without seeing the law; answers\n"
        "# found by other subagents reading the corpus (scripts/blind_eval.py), not our search;\n"
        "# judged: true = in a missed question's top 10 of our search, accepted by a judge.\n"
    )
    args.out.write_text(
        header + yaml.safe_dump(items, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    for line in dropped:
        print("dropped", line)
    print(f"{len(items)} questions -> {args.out}, {len(dropped)} dropped")


def main() -> None:
    global UNITS
    parser = argparse.ArgumentParser()
    parser.add_argument("--units", type=Path, default=UNITS, help="units file (see units)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("units")
    p.add_argument("--data-dir", type=Path, default=Path("data"))
    p.add_argument("--out", type=Path)
    p = sub.add_parser("grep", help="units whose path+text match every pattern (regex)")
    p.add_argument("patterns", nargs="+")
    p.add_argument("--title", help="regex on the document title")
    p.add_argument("--kind", help="document kinds, e.g. kodeks,qonun")
    p.add_argument("--doc", help="only this document id")
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--per-doc", type=int, default=3)
    p.add_argument("--context", type=int, default=150)
    p = sub.add_parser("titles", help="documents whose title matches")
    p.add_argument("pattern")
    p.add_argument("--limit", type=int, default=40)
    p = sub.add_parser("show")
    p.add_argument("document")
    p.add_argument("number", nargs="?")
    p.add_argument("--within", help="regex on the path when the number repeats")
    p = sub.add_parser("build")
    p.add_argument("labels", nargs="+", type=Path)
    p.add_argument("--out", type=Path, default=Path("eval/questions_blind.yaml"))
    p.add_argument("--pairs", type=Path, default=Path("data/eval/blind/pairs.jsonl"))
    p.add_argument("--judged", type=Path, help="JSON {id: [answers]} from judging misses")
    args = parser.parse_args()
    UNITS = args.units
    if args.command == "units" and args.out is None:
        args.out = UNITS
    {"units": export_units, "grep": grep, "titles": titles, "show": show, "build": build}[
        args.command
    ](args)


if __name__ == "__main__":
    main()
