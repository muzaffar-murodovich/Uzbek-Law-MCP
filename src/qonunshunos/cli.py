"""Command line interface: ``qonunshunos``."""

import argparse
import logging
from collections import Counter
from pathlib import Path

from qonunshunos import __version__
from qonunshunos.crawler.client import FetchError, LexClient, NotFound
from qonunshunos.crawler.pipeline import Workspace, fetch, parse, sample_ids


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
    return parser


def _report_line(lex_id: int, document, card) -> str:
    kinds = Counter(u.kind for u in document.units)
    status = card.status if card else "?"
    counts = " ".join(f"{k}={v}" for k, v in sorted(kinds.items())) or "-"
    warn = f"  warnings={len(document.warnings)}" if document.warnings else ""
    return (
        f"{lex_id:>9}  {status:<10} {document.content:<8} {counts:<28} {document.title[:60]}{warn}"
    )


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
            failed = 0
            for lex_id in ids:
                try:
                    fetch(client, ws, lex_id, force=args.force)
                    document, card = parse(ws, lex_id)
                except (NotFound, FetchError, ValueError) as exc:
                    failed += 1
                    print(f"{lex_id:>9}  ERROR {exc}")
                    continue
                print(_report_line(lex_id, document, card), flush=True)
                for warning in document.warnings:
                    print(f"           ! {warning}")
            return 1 if failed else 0

    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
