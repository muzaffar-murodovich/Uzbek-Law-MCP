"""Public pages: home (how to connect), privacy policy, terms of use, robots.txt."""

import logging
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date
from html import escape

import psycopg
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse

from qonunshunos.auth.pages import page

UPDATED = "2026-yil 6-noyabr"

log = logging.getLogger(__name__)

MONTHS = (
    "yanvar", "fevral", "mart", "aprel", "may", "iyun",
    "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
)  # fmt: skip

# Crawlers may read the public pages; the MCP endpoint and OAuth flow are not for them.
ROBOTS = """User-agent: *
Disallow: /mcp
Disallow: /auth/
Disallow: /authorize
Disallow: /token
Disallow: /register
Disallow: /revoke
Allow: /
"""

STATS_TTL = 600  # seconds


@dataclass(frozen=True)
class Stats:
    documents: int  # acts in force with searchable text
    updated: date | None  # last nightly update run


def date_uz(d: date) -> str:
    return f"{d.year}-yil {d.day}-{MONTHS[d.month - 1]}"


def load_stats(conn: psycopg.Connection) -> Stats:
    documents = conn.execute(
        "SELECT count(*) FROM documents WHERE status = 'in_force' AND content = 'html'"
    ).fetchone()[0]
    row = conn.execute("SELECT max(finished_at) FROM update_runs").fetchone()
    return Stats(documents, row[0].date() if row and row[0] else None)


def _contact(contact: str) -> str:
    if not contact:
        return "loyiha muallifiga"
    if "@" in contact and not contact.startswith("http"):
        return f"<a href='mailto:{escape(contact)}'>{escape(contact)}</a> manziliga"
    return f"<a href='{escape(contact)}'>{escape(contact)}</a> orqali"


def _coverage(stats: Stats | None) -> str:
    if stats is None:
        return ""
    text = (
        f"Bazada {stats.documents:,} ta amaldagi hujjat".replace(",", " ")
        + ": Konstitutsiya, kodekslar, qonunlar, Prezident va hukumat qarorlari, vazirlik"
        " va idoralarning roʻyxatdan oʻtgan hujjatlari. Faqat amaldagi tahrir."
    )
    if stats.updated:
        text += f" Har kecha yangilanadi, oxirgi yangilanish: {date_uz(stats.updated)}."
    return f"<p>{text}</p>"


def home(base_url: str, stats: Stats | None = None) -> HTMLResponse:
    mcp = escape(f"{base_url.rstrip('/')}/mcp")
    body = f"""
<h1>Qonunshunos</h1>
<p>AI yordamchingiz (Claude, ChatGPT, Cursor va boshqalar) Oʻzbekiston qonunchiligidan javob
topishi uchun MCP server. Manba — <a href="https://lex.uz">lex.uz</a> (Qonunchilik
maʼlumotlari milliy bazasi). Har bir javobda moddaga aniq havola beriladi.</p>
{_coverage(stats)}
<p>Xizmat bepul. Kuniga 30 ta qidiruv va 200 ta boshqa soʻrov, daqiqasiga 10 ta.
Kirish Google akkaunti orqali.</p>

<h2>Qanday ulanadi</h2>
<p>Server manzili: <code>{mcp}</code></p>
<ul>
<li><b>claude.ai / Claude Desktop:</b> Sozlamalar → Connectors → Add custom connector →
manzilni kiriting, soʻng Google orqali kiring.</li>
<li><b>ChatGPT:</b> Sozlamalar → Apps &amp; Connectors → Advanced settings → Developer mode,
keyin yangi konnektor yarating va manzilni kiriting.</li>
<li><b>Claude Code:</b> <code>claude mcp add --transport http qonunshunos {mcp}</code>,
keyin <code>/mcp</code> buyrugʻi bilan kiring.</li>
<li><b>Cursor va boshqalar:</b> “remote MCP server (Streamable HTTP)” sifatida shu manzilni
qoʻshing.</li>
</ul>

<h2>Muhim</h2>
<p>Javoblar umumiy maʼlumot, yuridik maslahat emas. Bu norasmiy loyiha: lex.uz va davlat
organlariga aloqasi yoʻq. Eng yangi hujjatlar bazada hali boʻlmasligi mumkin, shuning uchun
muhim masalada asl matnni lex.uz'da tekshiring va yuristga murojaat qiling.</p>
"""
    return page("Oʻzbekiston qonunchiligi uchun MCP server", body, wide=True)


def privacy(contact: str) -> HTMLResponse:
    body = f"""
<h1>Maxfiylik siyosati</h1>
<p class="muted">Oxirgi tahrir: {UPDATED}</p>

<h2>1. Nima saqlanadi</h2>
<ul>
<li><b>Google akkauntidan:</b> Google ID, email va ism. Parolingiz, kontaktlaringiz va Google
tokenlari bizga kelmaydi va saqlanmaydi.</li>
<li><b>Soʻrovlar:</b> qaysi vosita qachon chaqirilgani, qidiruv soʻzi yoki hujjat nomi
(300 belgigacha), natijalar soni va javob vaqti.</li>
<li><b>Ulangan ilovalar:</b> AI ilovasining nomi va manzili, kirish tokenlari (faqat
shifrlangan xesh koʻrinishida).</li>
</ul>

<h2>2. Nima uchun</h2>
<p>Kirish va kunlik limitlarni hisoblash, xizmatni suiisteʼmoldan himoya qilish va qidiruv
sifatini yaxshilash uchun. Maʼlumotlar reklama uchun ishlatilmaydi va sotilmaydi.</p>

<h2>3. Qancha vaqt</h2>
<p>Soʻrovlar matni 12 oy saqlanadi, keyin oʻchiriladi (faqat son va vaqt qoladi). Akkaunt
maʼlumotlari siz oʻchirishni soʻraguningizcha saqlanadi. Tokenlar muddati tugagach
oʻchiriladi.</p>

<h2>4. Qayerda</h2>
<p>Server Germaniyada (Hetzner maʼlumotlar markazi) joylashgan. Bu xizmatga kirish orqali siz
“Shaxsga doir maʼlumotlar toʻgʻrisida”gi Qonunning 15-moddasiga muvofiq yuqoridagi
maʼlumotlarning Oʻzbekiston hududidan tashqarida saqlanishiga rozilik bildirasiz. Biometrik
va genetik maʼlumotlar yigʻilmaydi.</p>

<h2>5. Kimga beriladi</h2>
<p>Hech kimga berilmaydi, qonunda bevosita nazarda tutilgan hollar bundan mustasno.
Savolingizning oʻzini AI ilovangiz (masalan, Anthropic yoki OpenAI) oʻz maxfiylik siyosatiga
koʻra qayta ishlaydi: biz faqat u bizga yuborgan soʻrovni koʻramiz.</p>

<h2>6. Huquqlaringiz</h2>
<p>Maʼlumotlaringizni koʻrish, tuzatish yoki akkauntni oʻchirishni soʻrash uchun
{_contact(contact)} murojaat qiling. Ulangan ilovani AI ilovangiz sozlamalarida istalgan payt
uzib qoʻyishingiz mumkin.</p>

<h2>7. Oʻzgarishlar</h2>
<p>Siyosat oʻzgarsa, shu sahifada yangi tahrir sanasi bilan eʼlon qilinadi.</p>
"""
    return page("Maxfiylik siyosati", body, wide=True)


def terms(contact: str) -> HTMLResponse:
    body = f"""
<h1>Foydalanish shartlari</h1>
<p class="muted">Oxirgi tahrir: {UPDATED}</p>
<ol>
<li>Qonunshunos — Oʻzbekiston qonunchiligi matnlarini AI yordamchilar uchun qidiradigan
bepul, norasmiy xizmat. Manba — lex.uz. Har bir javobda asl hujjatga havola beriladi.</li>
<li>Natijalar umumiy maʼlumot, yuridik maslahat emas. Matnlar lex.uz'dan avtomatik olinadi,
ularda kechikish yoki xato boʻlishi mumkin. Rasmiy matn — lex.uz'dagi matn.</li>
<li>AI yordamchining javobi uchun uning ishlab chiqaruvchisi va foydalanuvchining oʻzi
javobgar. Muhim qaror qabul qilishdan oldin yuristga murojaat qiling.</li>
<li>Bepul limitlar: kuniga 30 ta qidiruv, 200 ta boshqa soʻrov, daqiqasiga 10 ta. Limitlarni
chetlab oʻtish, avtomatik ommaviy yuklab olish va serverga zarar yetkazish taqiqlanadi.
Bunday hollarda akkaunt bloklanishi mumkin.</li>
<li>Xizmat “boricha” taqdim etiladi va istalgan payt oʻzgartirilishi yoki toʻxtatilishi
mumkin. Shartlar oʻzgarsa, shu sahifada eʼlon qilinadi.</li>
<li>Savollar boʻyicha {_contact(contact)} murojaat qiling.</li>
</ol>
"""
    return page("Foydalanish shartlari", body, wide=True)


def routes(
    base_url: str,
    contact: str = "",
    connection: Callable[[], AbstractContextManager[psycopg.Connection]] | None = None,
):
    cache: dict[str, tuple[float, Stats | None]] = {}

    def stats() -> Stats | None:
        if connection is None:
            return None
        hit = cache.get("stats")
        if hit and time.monotonic() - hit[0] < STATS_TTL:
            return hit[1]
        try:
            with connection() as conn:
                value = load_stats(conn)
        except Exception:  # the home page must render even without the database
            log.exception("home page stats failed")
            value = hit[1] if hit else None
        cache["stats"] = (time.monotonic(), value)
        return value

    async def home_page(_request: Request) -> HTMLResponse:
        return home(base_url, await run_in_threadpool(stats))

    async def robots(_request: Request) -> PlainTextResponse:
        return PlainTextResponse(ROBOTS)

    async def privacy_page(_request: Request) -> HTMLResponse:
        return privacy(contact)

    async def terms_page(_request: Request) -> HTMLResponse:
        return terms(contact)

    return [
        ("/", ["GET"], home_page),
        ("/robots.txt", ["GET"], robots),
        ("/maxfiylik", ["GET"], privacy_page),
        ("/shartlar", ["GET"], terms_page),
    ]
