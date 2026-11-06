"""Public pages: home (how to connect), privacy policy, terms of use."""

from html import escape

from starlette.requests import Request
from starlette.responses import HTMLResponse

from qonunshunos.auth.pages import page

UPDATED = "2026-yil 6-noyabr"


def _contact(contact: str) -> str:
    if not contact:
        return "loyiha muallifiga"
    if "@" in contact and not contact.startswith("http"):
        return f"<a href='mailto:{escape(contact)}'>{escape(contact)}</a> manziliga"
    return f"<a href='{escape(contact)}'>{escape(contact)}</a> orqali"


def home(base_url: str) -> HTMLResponse:
    mcp = escape(f"{base_url.rstrip('/')}/mcp")
    body = f"""
<h1>Qonunshunos</h1>
<p>AI yordamchingiz (Claude, ChatGPT, Cursor va boshqalar) Oʻzbekiston qonunchiligidan javob
topishi uchun MCP server. Manba — <a href="https://lex.uz">lex.uz</a> (Qonunchilik
maʼlumotlari milliy bazasi). Har bir javobda moddaga aniq havola beriladi.</p>
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


def routes(base_url: str, contact: str = ""):
    async def home_page(_request: Request) -> HTMLResponse:
        return home(base_url)

    async def privacy_page(_request: Request) -> HTMLResponse:
        return privacy(contact)

    async def terms_page(_request: Request) -> HTMLResponse:
        return terms(contact)

    return [
        ("/", ["GET"], home_page),
        ("/maxfiylik", ["GET"], privacy_page),
        ("/shartlar", ["GET"], terms_page),
    ]
