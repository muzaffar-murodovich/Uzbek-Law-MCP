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

    p = sub.add_parser("scope", help="stage 6: list every Latin act in force (by minor and year)")
    p.add_argument("--last-year", type=int, help="default: this year")

    p = sub.add_parser("crawl-full", help="stage 6: fetch and parse every act listed by scope")
    p.add_argument("--limit", type=int, help="stop after this many listed acts (a trial run)")
    p.add_argument("--no-notify", action="store_true", help="no Telegram progress messages")

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

    p = sub.add_parser("serve", help="run the MCP server (Streamable HTTP at /mcp)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--stdio", action="store_true", help="talk MCP over stdin/stdout instead")
    p.add_argument("--model", default=DEFAULT_MODEL, choices=sorted(MODELS))
    p.add_argument(
        "--no-auth", action="store_true", help="no OAuth and no limits (loopback hosts only)"
    )
    p.add_argument(
        "--no-access-log",
        action="store_true",
        help="do not log request lines (they carry one-time OAuth codes); nginx logs them",
    )

    p = sub.add_parser("user", help="list users, change limits, block (admin)")
    user_sub = p.add_subparsers(dest="user_command", required=True)
    q = user_sub.add_parser("list", help="users seen most recently, with today's calls")
    q.add_argument("--limit", type=int, default=50)
    q = user_sub.add_parser("show", help="one user: identities, limits, usage today")
    q.add_argument("user", help="id or e-mail")
    q = user_sub.add_parser("limit", help="override daily/minute limits: search=100 other=-")
    q.add_argument("user", help="id or e-mail")
    q.add_argument("changes", nargs="+", help="search=N, other=N, per_minute=N; '-' removes")
    q = user_sub.add_parser("block", help="block a user and revoke their tokens")
    q.add_argument("user", help="id or e-mail")
    q.add_argument("--reason")
    q = user_sub.add_parser("unblock")
    q.add_argument("user", help="id or e-mail")

    sub.add_parser("auth-cleanup", help="drop expired OAuth rows and query texts over 12 months")

    p = sub.add_parser("notify", help="send a Telegram message to the operator")
    p.add_argument("text", nargs="?", help="message; read from stdin when omitted")

    p = sub.add_parser("report", help="morning report: last update, users, backups, disk")
    p.add_argument("--send", action="store_true", help="send to Telegram instead of printing")

    p = sub.add_parser("update", help="nightly: new and amended acts from lex.uz → index")
    p.add_argument("--budget", type=int, default=400, help="max lex.uz requests (default 400)")
    p.add_argument("--dry-run", action="store_true", help="read the RSS feed only, write nothing")
    p.add_argument("--model", default=DEFAULT_MODEL, choices=sorted(MODELS))

    p = sub.add_parser("tool", help="call one MCP tool directly and print its answer")
    p.add_argument("name", help="search_law, get_article, get_document, ...")
    p.add_argument("params", nargs="*", help="key=value; repeat alt_queries=... for a list")

    p = sub.add_parser("eval", help="run the retrieval evaluation set")
    p.add_argument("--questions", type=Path, default=Path("eval/questions.yaml"))
    p.add_argument("--modes", default="fts,vector,hybrid")
    p.add_argument("--no-stem", action="store_true")
    p.add_argument("--no-alt", action="store_true", help="ignore alternative phrasings")
    p.add_argument("--alt-file", type=Path, help="JSON {id: [queries]} replacing alt")
    p.add_argument("--model", default=DEFAULT_MODEL, choices=sorted(MODELS))
    p.add_argument("--save", metavar="LABEL", help="write eval/results/<date>-<LABEL>.json")
    return parser


def _eval(args: argparse.Namespace) -> int:
    from qonunshunos.evaluation import format_report, load_questions, run, save_report
    from qonunshunos.index.embed import Embedder
    from qonunshunos.search.hybrid import search

    settings = Settings.from_env(args.data_dir)
    questions = load_questions(args.questions, args.alt_file)
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
        "alt": "none" if args.no_alt else str(args.alt_file or "questions"),
        "questions": str(args.questions),
    }
    print(format_report(report))
    if args.save:
        print(f"saved {save_report(report, args.questions.parent / 'results', args.save)}")
    return 0


LOOPBACK = ("127.0.0.1", "localhost", "::1")


def _serve(args: argparse.Namespace) -> int:
    from urllib.parse import urlparse

    from mcp.server.transport_security import TransportSecuritySettings

    from qonunshunos.auth.google import GoogleConfig
    from qonunshunos.auth.pages import AuthConfig
    from qonunshunos.mcp.server import Services, create_server

    settings = Settings.from_env(args.data_dir)
    services = Services(settings.dsn, settings.model_dir, args.model)
    if args.stdio:  # a local subprocess of the client: nobody else can reach it
        create_server(services).run("stdio")
        return 0
    loopback = args.host in LOOPBACK
    if args.no_auth and not loopback:
        print("error: --no-auth is only allowed on a loopback host")
        return 2
    auth = None
    public_url = settings.public_url or f"http://localhost:{args.port}"
    if not args.no_auth:
        google = None
        if settings.google_client_id and settings.google_client_secret:
            google = GoogleConfig(settings.google_client_id, settings.google_client_secret)
        dev_login = settings.dev_login and loopback and public_url.startswith("http://localhost")
        if google is None and not dev_login:
            print("error: set GOOGLE_CLIENT_ID/SECRET, or QONUNSHUNOS_DEV_LOGIN=1, or --no-auth")
            return 2
        auth = AuthConfig(public_url=public_url, google=google, dev_login=dev_login)
    server = create_server(services, auth, public_url=public_url, contact=settings.contact)

    # DNS-rebinding protection: accept the public host name that nginx forwards.
    public = urlparse(public_url)
    hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*", public.netloc]
    origins = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]
    origins.append(f"{public.scheme}://{public.netloc}")
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True, allowed_hosts=hosts, allowed_origins=origins
    )
    import uvicorn

    app = server.streamable_http_app(
        stateless_http=True, json_response=True, host=args.host, transport_security=security
    )
    log_mode = "no auth" if auth is None else f"OAuth issuer {public_url}"
    print(f"Qonunshunos MCP at http://{args.host}:{args.port}/mcp ({log_mode})", flush=True)
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
        access_log=not args.no_access_log,
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
    )
    return 0


def _parse_limit_changes(items: list[str]) -> dict:
    changes = {}
    for item in items:
        key, sep, value = item.partition("=")
        if not sep or key not in ("search", "other", "per_minute"):
            raise ValueError(f"expected search=N, other=N or per_minute=N, got {item!r}")
        changes[key] = None if value in ("-", "") else int(value)
    return changes


def _user(args: argparse.Namespace) -> int:
    from datetime import datetime

    from qonunshunos.auth import limits, users

    settings = Settings.from_env(args.data_dir)
    now = datetime.now(limits.TASHKENT)
    with connect(settings.dsn, vector=False) as conn:
        if args.user_command == "list":
            rows = users.overview(conn, limits.day_start(now), args.limit)
            print(f"{'id':>5}  {'via':<8} {'today':>5} {'search':>6}  {'last seen':<16} user")
            for user, providers, calls, searches in rows:
                seen = user.last_seen_at.astimezone(limits.TASHKENT) if user.last_seen_at else None
                flag = "  [BLOCKED]" if user.blocked else ""
                print(
                    f"{user.id:>5}  {providers:<8} {calls:>5} {searches:>6}  "
                    f"{seen.strftime('%Y-%m-%d %H:%M') if seen else '-':<16} "
                    f"{user.email or user.display_name or ''}{flag}"
                )
            return 0
        user = users.find(conn, args.user)
        if user is None:
            print(f"no such user: {args.user}")
            return 1
        if args.user_command == "limit":
            try:
                changes = _parse_limit_changes(args.changes)
            except ValueError as exc:
                print(f"error: {exc}")
                return 2
            user = users.set_limits(conn, user.id, changes)
        elif args.user_command == "block":
            users.block(conn, user.id, args.reason)
        elif args.user_command == "unblock":
            users.unblock(conn, user.id)
        user = users.get(conn, user.id)
        identities = conn.execute(
            "SELECT provider, coalesce(email, username, subject) FROM user_identities"
            " WHERE user_id = %s ORDER BY created_at",
            (user.id,),
        ).fetchall()
        used = {g: limits.count_today(conn, user.id, g, now) for g in ("search", "other")}
        lim = user.limits
        print(f"user {user.id}: {user.display_name or '-'} <{user.email or '-'}>")
        print("  via      " + ", ".join(f"{p}:{s}" for p, s in identities))
        print(f"  plan     {user.plan}  overrides {user.limits_override or '-'}")
        print(
            f"  today    search {used['search']}/{lim.search}, other {used['other']}/{lim.other},"
            f" {lim.per_minute}/min"
        )
        if user.blocked:
            print(f"  BLOCKED  {user.blocked_at:%Y-%m-%d %H:%M} {user.blocked_reason or ''}")
    return 0


LIST_PARAMS = {"alt_queries", "doc_types"}


def _tool(args: argparse.Namespace) -> int:
    from qonunshunos.mcp import tools
    from qonunshunos.mcp.server import Services

    fn = getattr(tools, args.name, None)
    if fn is None or args.name.startswith("_"):
        print(f"unknown tool {args.name}")
        return 2
    params: dict = {}
    for item in args.params:
        name, _, value = item.partition("=")
        if name in LIST_PARAMS:
            params.setdefault(name, []).append(value)
        else:
            params[name] = (
                int(value) if value.lstrip("-").isdigit() and name != "document" else value
            )
    settings = Settings.from_env(args.data_dir)
    services = Services(settings.dsn, settings.model_dir)
    try:
        print(services.run(args.name, params, fn, embed=args.name == "search_law"))
    finally:
        services.close()
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


def _full(args: argparse.Namespace, ws: Workspace) -> int:
    from qonunshunos.crawler.full import build_scope, crawl_scope, load_scope
    from qonunshunos.notify import NotifyError, send

    settings = Settings.from_env(args.data_dir)

    def notify(text: str) -> None:
        if getattr(args, "no_notify", False) or not settings.telegram_token:
            return
        try:
            send(settings.telegram_token, settings.telegram_chat_id, text)
        except NotifyError as exc:
            print(f"notify failed: {exc}")

    with LexClient() as client:
        if args.command == "scope":
            report = build_scope(client, ws, last_year=args.last_year)
            print(
                f"{report.listed} acts in {report.files} files "
                f"({report.fetched_files} fetched now); lex.uz says {report.total}"
            )
            for name in report.short:
                print(f"  short listing: {name}")
            return 0

        items = load_scope(ws)
        if not items:
            print("no scope listings: run `qonunshunos scope` first")
            return 1
        if args.limit:
            items = items[: args.limit]
        notify(f"Qonunshunos crawl boshlandi: {len(items)} ta hujjat")
        stats = crawl_scope(
            client,
            ws,
            items,
            total=len(items),
            notify=notify,
            say=lambda line: print(line, flush=True),
            state_file=ws.data_dir / "crawl-full.json",
        )
    print(stats.summary())
    notify(f"Qonunshunos crawl tugadi: {stats.summary()}")
    return 1 if stats.stopped else 0


class _LazyEmbedder:
    """Loads the ONNX model (≈300 MB) only when a changed document needs embeddings."""

    def __init__(self, model_dir: Path, model: str) -> None:
        self.model_dir, self.model, self._real = model_dir, model, None
        self.name = MODELS[model].name

    def _get(self):
        if self._real is None:
            from qonunshunos.index.embed import Embedder

            self._real = Embedder(self.model_dir, self.model)
        return self._real

    def passages(self, texts):
        return self._get().passages(texts)

    def query(self, text):
        return self._get().query(text)


def _notify(args: argparse.Namespace) -> int:
    import sys

    from qonunshunos.notify import morning_report, send

    settings = Settings.from_env(args.data_dir)
    if args.command == "notify":
        text = args.text if args.text is not None else sys.stdin.read()
    else:
        with connect(settings.dsn, vector=False) as conn:
            text = morning_report(conn, settings.backups_dir, settings.data_dir)
        if not args.send:
            print(text)
            return 0
    send(settings.telegram_token, settings.telegram_chat_id, text.strip() or "(boʻsh xabar)")
    return 0


def _update(args: argparse.Namespace, ws: Workspace) -> int:
    from qonunshunos.crawler.update import run_update

    settings = Settings.from_env(args.data_dir)
    embedder = _LazyEmbedder(settings.model_dir, args.model)
    with connect(settings.dsn) as conn, LexClient() as client:
        report = run_update(conn, client, ws, embedder, budget=args.budget, dry_run=args.dry_run)
    print(report.summary())
    for name in ("added", "changed", "lost_force", "pending"):
        for item in getattr(report, name):
            print(f"  {name:<10} {item['id']:>9}  {item['title'][:70]}")
    for item in report.rss_new:
        if item["links"]:
            print(f"  rss        {item['id']:>9}  {item['title'][:60]} → {item['links']}")
    for item in report.errors:
        print(f"  error      {item['id']:>9}  {item['error'][:90]}")
    # Errors on single documents are retried in their next turn; a failed RSS read raises.
    return 0


def _index(args: argparse.Namespace, ws: Workspace) -> int:
    from qonunshunos.crawler.full import requisites_only_ids
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
        amending = requisites_only_ids(ws)
        total = 0
        for lex_id in ids:
            document, card = load_parsed(ws, lex_id)
            count = index_document(
                conn,
                document,
                card,
                embedder,
                use_stem=not args.no_stem,
                force=args.force,
                requisites_only=lex_id in amending,
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

    if args.command == "serve":
        return _serve(args)

    if args.command == "user":
        return _user(args)

    if args.command == "auth-cleanup":
        from qonunshunos.auth.provider import cleanup

        with connect(Settings.from_env(args.data_dir).dsn, vector=False) as conn:
            counts = cleanup(conn)
        print(", ".join(f"{k}: {v}" for k, v in counts.items()))
        return 0

    if args.command == "tool":
        return _tool(args)

    if args.command == "update":
        return _update(args, ws)

    if args.command in ("notify", "report"):
        return _notify(args)

    if args.command == "parse":
        document, card = parse(ws, args.lex_id)
        print(_report_line(args.lex_id, document, card))
        for warning in document.warnings:
            print(f"  ! {warning}")
        return 0

    if args.command in ("scope", "crawl-full"):
        return _full(args, ws)

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
