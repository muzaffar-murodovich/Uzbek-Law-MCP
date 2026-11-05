"""Command line interface: ``qonunshunos``."""

import argparse
import dataclasses
import json
import logging
from collections import Counter
from pathlib import Path

from qonunshunos import __version__
from qonunshunos.config import Settings
from qonunshunos.crawler.client import FetchError, LexClient, NotFound
from qonunshunos.crawler.listing import FORM_LISTING, iter_listing
from qonunshunos.crawler.pipeline import (
    Workspace,
    fetch,
    load_parsed,
    parse,
    parsed_ids,
    sample_ids,
)
from qonunshunos.db import connect, migrate
from qonunshunos.index.embed import DEFAULT_MODEL, MODELS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qonunshunos")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="default: ./data")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("fetch", help="download a document page and its card1 into data/raw")
    p.add_argument("lex_id", type=int, help="Latin document id, e.g. -6257288")
    p.add_argument("--force", action="store_true", help="download again even if stored")

    p = sub.add_parser("parse", help="parse a stored document into data/parsed/<id>.json")
    p.add_argument("lex_id", type=int)

    p = sub.add_parser("crawl-sample", help="Constitution + codes in force: fetch, parse, report")
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("listing", help="save a lex.uz listing (all pages) as JSON")
    p.add_argument("form_id", type=int, help="document form, e.g. 3968 (Qonun)")
    p.add_argument("--out", type=Path, help="default: data/listings/form-<id>.json")
    p.add_argument("--max-pages", type=int, default=10_000, help="newest documents come first")

    p = sub.add_parser("crawl", help="fetch and parse the given documents")
    p.add_argument("lex_ids", type=int, nargs="*")
    p.add_argument("--ids-file", type=Path, help="text file with one lex id per line")
    p.add_argument("--force", action="store_true")

    sub.add_parser("db-migrate", help="create or upgrade the database schema (QONUNSHUNOS_DSN)")

    p = sub.add_parser("index", help="write parsed documents into the database")
    p.add_argument("lex_ids", type=int, nargs="*", help="default: everything in data/parsed")
    p.add_argument("--force", action="store_true", help="re-index unchanged documents too")
    p.add_argument("--fts-only", action="store_true", help="only recompute FTS vectors")
    p.add_argument("--no-stem", action="store_true", help="index FTS terms without stemming")
    p.add_argument("--model", default=DEFAULT_MODEL, choices=sorted(MODELS))

    p = sub.add_parser("search", help="hybrid search over the indexed documents")
    p.add_argument("query")
    p.add_argument("--alt", action="append", default=[], help="alternative phrasing")
    p.add_argument("--mode", default="hybrid", choices=["hybrid", "fts", "vector"])
    p.add_argument("--limit", type=int, default=8)
    p.add_argument("--no-stem", action="store_true")
    p.add_argument("--model", default=DEFAULT_MODEL, choices=sorted(MODELS))

    p = sub.add_parser("eval", help="run the retrieval evaluation set")
    p.add_argument("--questions", type=Path, default=Path("eval/questions.yaml"))
    p.add_argument("--modes", default="fts,vector,hybrid")
    p.add_argument("--no-stem", action="store_true")
    p.add_argument("--no-alt", action="store_true", help="ignore alternative phrasings")
    p.add_argument("--model", default=DEFAULT_MODEL, choices=sorted(MODELS))
    p.add_argument("--save", metavar="LABEL", help="write eval/results/<date>-<LABEL>.json")
    return parser


def _eval(args: argparse.Namespace) -> int:
    from qonunshunos.evaluation import format_report, load_questions, run, save_report
    from qonunshunos.index.embed import Embedder
    from qonunshunos.search.hybrid import search

    settings = Settings.from_env(args.data_dir)
    questions = load_questions(args.questions)
    embedder = Embedder(settings.model_dir, args.model)
    with connect(settings.dsn) as conn:

        def search_fn(q, mode):
            alt = [] if args.no_alt else q.alt
            return search(
                conn, embedder, q.question, alt, mode=mode, limit=10, use_stem=not args.no_stem
            )

        report = run(questions, search_fn, args.modes.split(","))
    report["settings"] = {
        "model": args.model,
        "stem": not args.no_stem,
        "alt": not args.no_alt,
        "questions": str(args.questions),
    }
    print(format_report(report))
    if args.save:
        print(f"saved {save_report(report, args.questions.parent / 'results', args.save)}")
    return 0


def _report_line(lex_id: int, document, card) -> str:
    kinds = Counter(u.kind for u in document.units)
    status = card.status if card else "?"
    counts = " ".join(f"{k}={v}" for k, v in sorted(kinds.items())) or "-"
    warn = f"  warnings={len(document.warnings)}" if document.warnings else ""
    return (
        f"{lex_id:>9}  {status:<10} {document.content:<8} {counts:<28} {document.title[:60]}{warn}"
    )


def _read_ids(path: Path) -> list[int]:
    ids = []
    for line in path.read_text(encoding="utf-8").splitlines():
        token = line.split("#", 1)[0].strip()
        if token:
            ids.append(int(token.split()[0]))
    return ids


def _crawl(client: LexClient, ws: Workspace, ids: list[int], force: bool) -> int:
    failed = 0
    for lex_id in ids:
        try:
            fetch(client, ws, lex_id, force=force)
            document, card = parse(ws, lex_id)
        except (NotFound, FetchError, ValueError) as exc:
            failed += 1
            print(f"{lex_id:>9}  ERROR {exc}")
            continue
        print(_report_line(lex_id, document, card), flush=True)
        for warning in document.warnings:
            print(f"           ! {warning}")
    return 1 if failed else 0


def _index(args: argparse.Namespace, ws: Workspace) -> int:
    from qonunshunos.index.embed import Embedder
    from qonunshunos.index.writer import index_document, rebuild_fts, refresh_fts_stats

    settings = Settings.from_env(args.data_dir)
    with connect(settings.dsn) as conn:
        if args.fts_only:
            count = rebuild_fts(conn, use_stem=not args.no_stem)
            print(f"recomputed FTS for {count} chunks")
            return 0
        embedder = Embedder(settings.model_dir, args.model)
        ids = args.lex_ids or parsed_ids(ws)
        total = 0
        for lex_id in ids:
            document, card = load_parsed(ws, lex_id)
            count = index_document(
                conn, document, card, embedder, use_stem=not args.no_stem, force=args.force
            )
            state = "unchanged" if count is None else f"{count} chunks"
            print(f"{lex_id:>9}  {state:<12} {document.title[:70]}", flush=True)
            total += count or 0
        if total:
            refresh_fts_stats(conn)
        print(f"{len(ids)} documents, {total} new chunks")
    return 0


def _search(args: argparse.Namespace) -> int:
    from qonunshunos.index.embed import Embedder
    from qonunshunos.search.hybrid import search

    settings = Settings.from_env(args.data_dir)
    embedder = Embedder(settings.model_dir, args.model)
    with connect(settings.dsn) as conn:
        hits = search(
            conn,
            embedder,
            args.query,
            args.alt,
            mode=args.mode,
            limit=args.limit,
            use_stem=not args.no_stem,
        )
    for n, hit in enumerate(hits, start=1):
        label = f"{hit.unit_number}-{hit.kind}" if hit.unit_number else hit.kind
        ranks = " ".join(f"{k}:{v}" for k, v in sorted(hit.ranks.items()))
        print(f"{n}. {hit.document}, {label}. {hit.unit_title or ''}")
        print(f"   {hit.url}   score={hit.score:.4f} {ranks}")
        print(f"   {hit.snippet[:200]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if args.command is None:
        parser.print_help()
        return 0

    ws = Workspace(args.data_dir)

    if args.command == "db-migrate":
        applied = migrate(Settings.from_env(args.data_dir).dsn)
        print(f"applied: {', '.join(applied)}" if applied else "schema is up to date")
        return 0

    if args.command == "index":
        return _index(args, ws)

    if args.command == "search":
        return _search(args)

    if args.command == "eval":
        return _eval(args)

    if args.command == "parse":
        document, card = parse(ws, args.lex_id)
        print(_report_line(args.lex_id, document, card))
        for warning in document.warnings:
            print(f"  ! {warning}")
        return 0

    with LexClient() as client:
        if args.command == "fetch":
            try:
                fetch(client, ws, args.lex_id, force=args.force)
            except (NotFound, FetchError) as exc:
                print(f"error: {exc}")
                return 1
            print(f"saved {args.lex_id} to {ws.raw.root}")
            return 0

        if args.command == "crawl-sample":
            ids = sample_ids(client)
            print(f"{len(ids)} documents in the sample")
            return _crawl(client, ws, ids, args.force)

        if args.command == "crawl":
            ids = list(args.lex_ids)
            if args.ids_file:
                ids += _read_ids(args.ids_file)
            return _crawl(client, ws, ids, args.force)

        if args.command == "listing":
            rows = list(
                iter_listing(client, f"{FORM_LISTING}{args.form_id}", max_pages=args.max_pages)
            )
            out = args.out or args.data_dir / "listings" / f"form-{args.form_id}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            payload = [dataclasses.asdict(r) for r in rows]
            out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
            in_force = sum(1 for r in rows if r.in_force)
            print(f"{len(rows)} documents ({in_force} in force) → {out}")
            return 0

    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
