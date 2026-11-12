"""MCP server: tools, prompt and resources over Streamable HTTP (or stdio)."""

import logging
import time
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Annotated, Literal

import psycopg
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from qonunshunos import __version__, site
from qonunshunos.auth import limits, users
from qonunshunos.auth.pages import AuthConfig
from qonunshunos.auth.pages import routes as auth_routes
from qonunshunos.auth.provider import SCOPE, Provider
from qonunshunos.index.embed import DEFAULT_MODEL, Embed, Embedder
from qonunshunos.mcp import tools
from qonunshunos.mcp.tools import Result
from qonunshunos.search.rerank import Rerank, Reranker, rerank_top

log = logging.getLogger(__name__)

DocKind = Literal[
    "konstitutsiya", "kodeks", "qonun", "farmon", "qaror", "vm_qarori", "farmoyish", "buyruq"
]

INSTRUCTIONS = """\
Qonunshunos searches the legislation of the Republic of Uzbekistan (source: lex.uz, the \
National Database of Legislation). Texts are in Uzbek (Latin script); only current editions of \
acts in force are indexed.

How to answer a legal question:
1. Call search_law. Write `query` in Uzbek (Latin script), translating from Russian, English or \
Cyrillic if needed, and ALWAYS add 1-2 `alt_queries` that rephrase the question in the formal \
wording a statute would use (e.g. "ishdan haydash" -> "mehnat shartnomasini ish beruvchining \
tashabbusiga ko'ra bekor qilish").
2. Read the relevant articles in full with get_article: search snippets are cut.
3. Answer in the user's language. Cite every rule with the act, article number and its lex.uz \
link. Do not cite articles you have not read.
4. Say that the answer is general information, not legal advice. The newest acts may not be in \
the database yet; if nothing fits, say so instead of guessing.
"""

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False, idempotent_hint=True)

DocumentRef = Annotated[
    str,
    Field(
        description=(
            'Document id ("-6257288"), lex.uz URL, number ("OʻRQ-642", "PF-60"), '
            'abbreviation ("MK", "JK", "SK") or name ("Mehnat kodeksi").'
        )
    ),
]
PageArg = Annotated[int, Field(ge=1, description="Page of a long text, from 1.")]


class Services:
    """Connection pool and embedding model, shared by all tool calls."""

    def __init__(
        self,
        dsn: str,
        model_dir,
        model: str = DEFAULT_MODEL,
        embedder: Embed = None,
        reranker: Rerank | None = None,
    ):
        self.dsn = dsn
        self.model_dir = model_dir
        self.model = model
        self.embedder: Embed | None = embedder
        # Real models are loaded on first use only when none were passed in (tests pass fakes).
        self._load_reranker = embedder is None and reranker is None
        self.reranker: Rerank | None = reranker
        self.pool: ConnectionPool | None = None
        self.window = limits.MinuteWindow()

    def open(self) -> None:
        if self.pool is None:
            from pgvector.psycopg import register_vector

            self.pool = ConnectionPool(
                self.dsn,
                min_size=1,
                max_size=4,
                kwargs={"autocommit": True},
                configure=register_vector,
                open=True,
            )
        if self.embedder is None:
            self.embedder = Embedder(self.model_dir, self.model)
        if self._load_reranker and self.reranker is None and rerank_top() > 0:
            self.reranker = Reranker(self.model_dir)

    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection]:
        self.open()
        with self.pool.connection() as conn:
            yield conn

    def close(self) -> None:
        if self.pool is not None:
            self.pool.close()
            self.pool = None

    def run(self, name: str, args: dict, fn: Callable[..., Result], *, embed: bool = False) -> str:
        """Run one tool with a pooled connection and record it in ``usage_events``.

        With OAuth on, the caller comes from the access token and the call must fit the user's
        limits; a refused call returns an explanation (not an error) and is not counted.
        """
        self.open()
        token = get_access_token()
        user_id = int(token.subject) if token and token.subject else None
        started = time.perf_counter()
        result: Result | None = None
        refusal: str | None = None
        try:
            with self.pool.connection() as conn:
                if user_id is not None:
                    user = users.get(conn, user_id)
                    user_limits = user.limits if user else limits.PLANS["free"]
                    refusal = limits.check(conn, user_id, name, user_limits, self.window)
                    if refusal:
                        return refusal
                extra = (self.embedder,) if embed else ()
                kwargs = {**args, "reranker": self.reranker} if embed and self.reranker else args
                result = fn(conn, *extra, **kwargs)
                return result.text
        finally:
            elapsed = int((time.perf_counter() - started) * 1000)
            self._log(name, args, elapsed, result, user_id, refused=refusal is not None)

    def _log(
        self,
        name: str,
        args: dict,
        elapsed: int,
        result: Result | None,
        user_id: int | None,
        *,
        refused: bool = False,
    ) -> None:
        logged = {
            k: (v[:300] if isinstance(v, str) else v) for k, v in args.items() if v is not None
        }
        try:
            with self.pool.connection() as conn:
                conn.execute(
                    "INSERT INTO usage_events"
                    " (user_id, tool, latency_ms, result_count, ok, counted, args)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        user_id,
                        name,
                        elapsed,
                        result.count if result else None,
                        result is not None or refused,
                        not refused,
                        Jsonb(logged),
                    ),
                )
        except Exception:  # the answer matters more than its statistics
            log.exception("could not record usage of %s", name)


def auth_settings(public_url: str) -> AuthSettings:
    base = public_url.rstrip("/")
    return AuthSettings(
        issuer_url=base,
        resource_server_url=f"{base}/mcp",
        validate_token_resource=True,
        required_scopes=[SCOPE],
        client_registration_options=ClientRegistrationOptions(
            enabled=True, valid_scopes=[SCOPE], default_scopes=[SCOPE]
        ),
        revocation_options=RevocationOptions(enabled=True),
        service_documentation_url=f"{base}/",
    )


def create_server(
    services: Services,
    auth: AuthConfig | None = None,
    *,
    public_url: str = "http://localhost:8000",
    contact: str = "",
) -> MCPServer:
    """The MCP server; with ``auth`` it is also an OAuth 2.1 authorization server."""

    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[None]:
        services.open()
        try:
            yield
        finally:
            services.close()

    provider = Provider(services.connection, auth.public_url) if auth else None
    server = MCPServer(
        "Qonunshunos",
        title="Qonunshunos — Oʻzbekiston qonunchiligi",
        instructions=INSTRUCTIONS,
        website_url="https://lex.uz",
        version=__version__,
        lifespan=lifespan,
        auth=auth_settings(auth.public_url) if auth else None,
        auth_server_provider=provider,
    )
    pages = site.routes(auth.public_url if auth else public_url, contact, services.connection)
    if auth:
        pages += auth_routes(provider, auth, services.connection)
    for path, methods, handler in pages:
        server.custom_route(path, methods=methods, include_in_schema=False)(handler)
    run = services.run

    @server.tool(annotations=READ_ONLY, title="Qonunchilikdan qidirish")
    def search_law(
        query: Annotated[
            str,
            Field(
                max_length=1000,
                description="The question in Uzbek, Latin script (translate if needed).",
            ),
        ],
        alt_queries: Annotated[
            list[str],
            Field(
                max_length=2,
                description=(
                    "1-2 rephrasings in formal statutory Uzbek, e.g. 'ishdan haydash' -> "
                    "'mehnat shartnomasini ish beruvchining tashabbusiga koʻra bekor qilish'. "
                    "Strongly improves results."
                ),
            ),
        ] = [],  # noqa: B006 (pydantic copies defaults)
        doc_types: Annotated[
            list[DocKind] | None, Field(description="Only these kinds of acts.")
        ] = None,
        limit: Annotated[int, Field(ge=1, le=15)] = 8,
    ) -> str:
        """Hybrid (keyword + semantic) search over articles of Uzbek legislation in force.

        Returns the best matching articles with act, article number, status, lex.uz link and a
        short snippet. Snippets are incomplete: read the article with get_article before
        answering.
        """
        args = {"query": query, "alt_queries": alt_queries, "doc_types": doc_types, "limit": limit}
        return run("search_law", args, tools.search_law, embed=True)

    @server.tool(annotations=READ_ONLY, title="Moddaning matni")
    def get_article(
        document: DocumentRef,
        article: Annotated[
            str, Field(description='Article or clause number: "161", "10¹", "10-1", "5-band".')
        ],
        page: PageArg = 1,
    ) -> str:
        """Full text of one article (modda) or clause (band) of an act, with its lex.uz link,
        status and latest amendments."""
        args = {"document": document, "article": article, "page": page}
        return run("get_article", args, tools.get_article)

    @server.tool(annotations=READ_ONLY, title="Hujjat rekvizitlari va mundarijasi")
    def get_document(document: DocumentRef, page: PageArg = 1) -> str:
        """Requisites of an act (kind, number, dates, status, issuing body) and its table of
        contents: parts, chapters and their article ranges, each with a `#N` reference for
        get_section."""
        return run("get_document", {"document": document, "page": page}, tools.get_document)

    @server.tool(annotations=READ_ONLY, title="Bob yoki boʻlim matni")
    def get_section(
        document: DocumentRef,
        section: Annotated[
            str,
            Field(
                description=(
                    'Reference from get_document ("#14"), a label ("12-bob", "II boʻlim", '
                    '"2-ilova") or part of the heading.'
                )
            ),
        ],
        page: PageArg = 1,
    ) -> str:
        """Full text of a chapter, section or annex with all its articles (paged)."""
        args = {"document": document, "section": section, "page": page}
        return run("get_section", args, tools.get_section)

    @server.tool(annotations=READ_ONLY, title="Hujjatni topish")
    def find_document(
        query: Annotated[
            str,
            Field(
                max_length=300,
                description='Name or number: "Taʼlim toʻgʻrisida", "OʻRQ-637", "PF-60".',
            ),
        ],
        doc_type: DocKind | None = None,
        year: Annotated[int | None, Field(ge=1990, le=2100, description="Adoption year.")] = None,
        include_lost_force: Annotated[
            bool, Field(description="Also list acts that lost force (requisites only).")
        ] = False,
        limit: Annotated[int, Field(ge=1, le=20)] = 10,
    ) -> str:
        """Find acts by name or number (not by content: use search_law for that)."""
        args = {
            "query": query,
            "doc_type": doc_type,
            "year": year,
            "include_lost_force": include_lost_force,
            "limit": limit,
        }
        return run("find_document", args, tools.find_document)

    @server.tool(annotations=READ_ONLY, title="Amaldagi kodekslar")
    def list_codes() -> str:
        """The Constitution and all codes in force, with ids and abbreviations."""
        return run("list_codes", {}, tools.list_codes)

    @server.prompt(name="yuridik_savol", title="Yuridik savol")
    def yuridik_savol(
        savol: Annotated[str, Field(description="Foydalanuvchining savoli")],
    ) -> str:
        """Answer a legal question from Uzbek legislation with exact article links."""
        return (
            f"Savol: {savol}\n\n"
            "Oʻzbekiston qonunchiligi asosida javob ber:\n"
            "1. `search_law`ni chaqir: `query` — savol oʻzbek tilida (lotin), `alt_queries` — "
            "qonun matnidagi rasmiy iboralar bilan 1–2 ta qayta ifoda.\n"
            "2. Mos moddalarni `get_article` bilan toʻliq oʻqi. Kerak boʻlsa qayta qidir.\n"
            "3. Qisqa va aniq javob ber. Har bir qoidaga hujjat nomi, modda raqami va lex.uz "
            "havolasini qoʻsh. Oʻqimagan moddangga tayanma.\n"
            "4. Mos modda topilmasa, buni ochiq ayt.\n"
            "5. Oxirida yoz: “Bu umumiy maʼlumot, yuridik maslahat emas. Muhim masalada "
            "advokat yoki yuristga murojaat qiling.”"
        )

    @server.resource(
        "lex://document/{document_id}",
        name="document",
        mime_type="text/markdown",
        description="Requisites and table of contents of an act.",
    )
    def document_resource(document_id: str) -> str:
        return run("resource_document", {"document": document_id}, tools.get_document)

    @server.resource(
        "lex://document/{document_id}/article/{article}",
        name="article",
        mime_type="text/markdown",
        description="Full text of one article.",
    )
    def article_resource(document_id: str, article: str) -> str:
        args = {"document": document_id, "article": article}
        return run("resource_article", args, tools.get_article)

    @server.custom_route("/healthz", methods=["GET"], include_in_schema=False)
    async def healthz(_request: Request) -> JSONResponse:
        try:
            services.open()
            with services.pool.connection(timeout=3) as conn:
                conn.execute("SELECT 1")
        except Exception as exc:
            return JSONResponse({"ok": False, "error": type(exc).__name__}, status_code=503)
        return JSONResponse({"ok": True, "version": __version__})

    return server
