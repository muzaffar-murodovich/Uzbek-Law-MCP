# Qonunshunos — loyiha rejasi

> **Qonunshunos** — ishchi (vaqtinchalik) nom.

O'zbekiston Respublikasi qonunchiligiga oid savollarga javob topishda yordam beradigan masofaviy
(remote) MCP server. Hozircha xizmat to'liq bepul, pullik tariflar keyinroq qo'shiladi.

## 1. Qabul qilingan qarorlar

| Mavzu | Qaror |
|---|---|
| Nom | Qonunshunos (ishchi nom) |
| Manba | lex.uz (Qonunchilik ma'lumotlari milliy bazasi), mahalliy bazaga yuklab olinadi va indekslanadi. Har bir javobda lex.uz'ga havola beriladi. Pullik tariflar ishga tushishidan oldin "Adolat" markazining yozma roziligi olinadi (3-bo'lim) |
| Qamrov (MVP) | Qonun hujjatlari (Konstitutsiya, kodekslar, qonunlar), Prezident hujjatlari, Hukumat qarorlari, vazirlik va idoralar hujjatlari. Keyin: mahalliy hokimiyat qarorlari, xalqaro shartnomalar, sud amaliyoti |
| Til | Hozircha o'zbek (lotin). Keyin: o'zbek (kirill), rus |
| Qidiruv | Gibrid: to'liq matnli (kalit so'z) + semantik (embedding), natijalar RRF bilan birlashtiriladi |
| Embedding | Hetzner serverning o'zida, ochiq ko'p tilli model |
| Tahrirlar | Faqat amaldagi tahrir. Kuchini yo'qotgan hujjatlarning faqat rekvizitlari saqlanadi, matni indekslanmaydi |
| Yangilash | Har kuni tunda avtomatik |
| Stek | Python: MCP Python SDK (FastMCP) + Starlette/FastAPI |
| Joylashuv | Hetzner, 4 GB RAM / 2 vCPU (keyin kuchliroq server) |
| Transport | Streamable HTTP (remote MCP) |
| Mijozlar | claude.ai, Claude Desktop, Claude Code, ChatGPT, Cursor — OAuth 2.1 orqali |
| Kirish | Google (Gmail) va Telegram orqali |
| Bepul limit | Kuniga 3 ta qidiruv (`search_law`). Boshqa vositalar (modda o'qish va h.k.) uchun kuniga 20 ta chaqiruv |
| To'lov | Hozircha hamma narsa bepul. Pullik tariflar (Payme/Click) keyinroq qo'shiladi. Foydalanish statistikasi boshidan yoziladi, administrator foydalanuvchiga alohida limit berishi mumkin |

## 2. 0-bosqich natijalari (lex.uz tadqiqoti)

Batafsil: [docs/research/lexuz.md](docs/research/lexuz.md). Qisqacha:

- **Lotin matni bor:** `lex.uz/docs/-{id}` (manfiy ID). Prezident va Hukumat hujjatlarining lotin
  versiyalari soni kirill versiyalari soniga deyarli teng.
- **HTML tuzilishi toza:** har bir element (bob, modda, xatboshi) o'z turiga ega
  (`TEXT_HEADER_DEFAULT` — bo'lim/bob, `CLAUSE_DEFAULT` — modda, `ACT_TEXT` — matn) va doimiy ID
  bilan keladi. Shu tufayli javobda aniq moddaga havola berish mumkin:
  `lex.uz/docs/-6257288#-6257549` (Mehnat kodeksi, 1-modda).
- **Rekvizitlar** (turi, raqami, sanasi, holati, kuchga kirish sanasi): `/actinfo/card1/{id}`.
  Klassifikator kodlari: `/actinfo/card2/{id}`. Har bir modda uchun mavzu kodlari (OKOZ) va
  "qaysi hujjat bilan o'zgartirilgan" ma'lumoti sahifaning o'zida bor.
- **Yangilanishlar:** RSS (`/uz/rss`) va "bugun e'lon qilinganlar" ro'yxati orqali kuzatiladi.
- `robots.txt` va sitemap yo'q. Ro'yxatlar 20 tadan, ASP.NET postback bilan sahifalanadi.
- Eng yangi hujjatlar dastlab faqat PDF ko'rinishida chiqadi, HTML matn keyinroq qo'shiladi.
  Farmon va qarorlarda modda yo'q: asosiy birlik — band, ilovalar (nizom, ro'yxat) alohida
  bloklar bilan ajratilgan. Amaldagi kodekslar — 20 ta (lotin).
- **Hajm:** MVP qamrovida ≈34 ming lotin hujjat, shundan ≈22 mingtasi amalda (taxmin).
  Yuklab olish 1–1,5 sutka (2 soniyada 1 so'rov tezligida), embedding 2 vCPU'da 4–8 soat. Demak,
  boshlang'ich indekslashni Hetzner serverning o'zida bajarsa bo'ladi.
- lex.uz'ning **o'z AI platformasi bor:** ai.lex.uz ("LexAI").

## 3. Huquqiy masala ⚠️

- "Mualliflik huquqi va turdosh huquqlar to'g'risida"gi Qonunning
  [8-moddasi](https://lex.uz/docs/-1022944#-1023047)ga ko'ra, rasmiy hujjatlar (qonunlar,
  qarorlar va h.k.) mualliflik huquqi obyekti emas.
- Lekin lex.uz'ning [Axborotni taqdim etish shartlari](https://lex.uz/uz/axborot)da
  shunday yozilgan: axborot faqat shaxsiy maqsadlarda ishlatiladi, *"daromad olish maqsadida
  maʼlumotlardan nusxa olish, tarqatish, sotish, berish resurs egasining yozma roziligisiz
  taqiqlanadi"*. Resurs egasi — Adliya vazirligi qoshidagi "Adolat" milliy huquqiy axborot markazi.
- Shartlarning o'zi bir xil ma'noda emas: bir joyda axborotdan "faqat shaxsiy maqsadlarda"
  foydalanish mumkinligi aytilgan, boshqa joyda boshqa resurslarda lex.uz'ga havola qilgan holda
  foydalanishga yo'l qo'yiladi. Aniq taqiq esa daromad olish maqsadidagi foydalanishga tegishli.
- **Qaror (2026-11-05):** hozircha xizmat to'liq bepul. Har bir javobda lex.uz'dagi asl hujjatga
  havola va manba ko'rsatiladi. Bepul xizmatni to'liq qamrov bilan ommaga ochish uchun rozilik
  kutilmaydi.
- **"Adolat" markaziga xat** ([loyiha](docs/adolat-markazi-xat.md)) loyihaga pullik tariflar
  qo'shilganda yuboriladi. Shartlarga ko'ra rozilik daromad olishdan oldin kerak. Shuning uchun xat
  to'lov bosqichi boshlanganda yuboriladi va yozma rozilik kelmaguncha pullik tariflar yoqilmaydi.
  Reklama kabi boshqa daromad manbalari uchun ham shu tartib amal qiladi.

## 4. Arxitektura

```
                 ┌──────────────────────── Hetzner (Docker Compose) ───────────────────────┐
 MCP mijoz ──TLS──► Caddy (HTTPS, avtomatik sertifikat)                                      │
 (claude.ai,     │    │                                                                     │
  ChatGPT, ...)  │    ├─► app: MCP server (/mcp) + OAuth server (/authorize, /token, ...)   │
                 │    │        │  kirish: Google (OIDC), Telegram Login                      │
                 │    │        ▼                                                             │
                 │    │   PostgreSQL 16 + pgvector + pg_trgm                                 │
                 │    │        ▲                                                             │
                 │    └─ worker: kunlik cron → lex.uz crawler → parser → chunk → embedding  │
                 └──────────────────────────────────────────────────────────────────────────┘
```

- **PostgreSQL + pgvector** — bitta bazada hujjatlar, FTS indeksi, vektorlar, foydalanuvchilar,
  OAuth tokenlar va statistika saqlanadi.
- **Embedding: `intfloat/multilingual-e5-small`** (ONNX, int8, `fastembed`/`onnxruntime` orqali).
  ~250 MB RAM oladi, vektori 384 o'lchamli, `halfvec` sifatida saqlanadi. Kuchliroq serverga o'tganda
  `bge-m3` yoki `multilingual-e5-base`'ga almashtiriladi: model konfiguratsiyada ko'rsatiladi,
  qayta indekslash uchun skript bo'ladi.
- **To'liq matnli qidiruv:** o'zbek tili uchun stemmer yo'q. Shuning uchun `simple` konfiguratsiya
  ishlatiladi va unga o'zimizning normalizatsiya qo'shiladi: apostroflar (`oʻ o' o‘ o'` → bitta
  shakl), pastki registr, oddiy qo'shimchalarni kesish. `pg_trgm` faqat hujjat nomi va raqami
  bo'yicha xatoli qidiruv uchun ishlatiladi.
- **4 GB RAM:** Postgres `shared_buffers≈1GB`, app va model ≈1 GB, qolgani OS keshiga.
  Bu chegaraga yaqin, lekin MVP uchun yetadi.

## 5. Ma'lumotlar modeli (soddalashtirilgan)

```
documents       id, lex_id, title, doc_type, form, number, issuing_body, adopted_at,
                entry_into_force_at, status, lost_force_at, lang, url, content_hash,
                fetched_at, updated_at
sections        id, document_id, parent_id, kind (qism/bo'lim/bob/modda/band), number, title,
                text, path ("II bo'lim > 5-bob > 37-modda"), lex_elem_id, okoz_codes,
                last_changed_by, ord
chunks          id, section_id, document_id, text, text_norm, tsv, embedding halfvec(384)
doc_links       from_document_id, from_elem_id, to_document_id, to_elem_id

users           id, display_name, plan, limits_override, created_at, blocked_at
user_identities user_id, provider (google|telegram), subject, email, username
oauth_clients, oauth_codes, oauth_tokens
usage_events    user_id, tool, ts, latency_ms, result_count, counted (limitga kirdimi)
```

Asosiy birlik — **modda**. Uzun moddalar qism yoki band bo'yicha bo'linadi. Har bir bo'lakka
kontekst sarlavhasi qo'shiladi, masalan: "Mehnat kodeksi, 161-modda. Mehnat shartnomasini ish
beruvchining tashabbusiga ko'ra bekor qilish".

## 6. MCP interfeysi

### Tools

| Tool | Vazifasi | Limit |
|---|---|---|
| `search_law(query, alt_queries?, doc_types?, limit=8)` | Gibrid qidiruv, faqat amaldagi hujjatlar bo'yicha. `alt_queries` (≤2) bilan bitta chaqiruvda bir nechta ifoda qidiriladi, bu bitta qidiruv deb sanaladi | 3/kun |
| `get_article(document, article)` | Moddaning to'liq matni ("Mehnat kodeksi", "161") | 20/kun* |
| `get_document(document_id)` | Rekvizitlar + mundarija | 20/kun* |
| `get_section(document_id, path)` | Bob yoki bo'lim matni (sahifalab) | 20/kun* |
| `find_document(title_or_number, doc_type?, year?)` | Hujjatni nomi yoki raqami bo'yicha topish ("PF-60", "OʻRQ-963") | 20/kun* |
| `list_codes()` | Amaldagi kodekslar ro'yxati | limitsiz |

\* Bu to'rt vosita uchun umumiy limit.

Tamoyillar:

- Har bir natijada moddaga aniq **havola** (`lex.uz/docs/-{id}#{elem}`), hujjat holati va oxirgi
  o'zgartirish ma'lumoti bo'ladi.
- Javoblar ixcham bo'ladi (token tejash uchun), uzun matn sahifalanadi.
- Kuchini yo'qotgan hujjat so'ralsa, uning matni berilmaydi. O'rniga "kuchini yo'qotgan, sana,
  sababi" haqida ma'lumot qaytariladi.

### Prompt va resurslar

- Prompt `yuridik_savol` javob berish tartibini belgilaydi: avval qidirish, moddalarni o'qish,
  javobda aniq moddalarga havola berish, "bu yuridik maslahat emas" ogohlantirishini qo'shish.
- Resurslar: `lex://document/{id}`, `lex://document/{id}/article/{n}`.

## 7. Kirish va limitlar

- **OAuth 2.1 avtorizatsiya serveri** (MCP talabi bo'yicha): Dynamic Client Registration, PKCE,
  `/.well-known/oauth-protected-resource` va `/.well-known/oauth-authorization-server`.
  `/authorize` sahifasida ikkita tugma bo'ladi: "Google orqali kirish" va "Telegram orqali kirish".
- **Google:** OpenID Connect, faqat `openid email profile` ruxsatlari. Google Cloud'da OAuth ilova
  ochiladi, buning uchun domen va maxfiylik siyosati sahifasi kerak.
- **Telegram:** Telegram Login Widget. BotFather'da bot ochiladi va `/setdomain` bilan domenga
  bog'lanadi. Server javobni bot tokeni bilan HMAC-SHA256 orqali tekshiradi.
- Bitta akkauntga Google va Telegram ikkalasini ham ulash mumkin.
- **Limitlar:** bepul tarifda kuniga 3 ta `search_law` va 20 ta boshqa chaqiruv. Hisoblagich har
  kuni 00:00 da (Toshkent vaqti) nolga tushadi. Limit tugaganda vosita xato emas, o'zbekcha xabar
  qaytaradi ("Bugungi bepul limit tugadi, ertaga 00:00 dan keyin qayta urinib ko'ring"). Shunda AI
  yordamchi buni foydalanuvchiga tushuntira oladi.
- Administrator CLI orqali foydalanuvchiga tarif yoki alohida limit beradi. Barcha qiymatlar
  konfiguratsiyada saqlanadi.

## 8. Bosqichlar

| # | Bosqich | Muddat | Holati |
|---|---|---|---|
| 0 | lex.uz tadqiqoti | 1–2 kun | ✅ bajarildi |
| 1 | Parser + crawler (avval namunaviy to'plamda) | 1 hafta | ✅ bajarildi (namunaviy to'plam) |
| 2 | Indekslash, gibrid qidiruv, baholash to'plami | 1 hafta | |
| 3 | MCP server va tool'lar | 3–4 kun | |
| 4 | OAuth, Google/Telegram kirish, limitlar | 1 hafta | domen kerak |
| 5 | Hetzner'ga deploy, zaxira nusxa, monitoring, kunlik yangilash | 2–3 kun | |
| 6 | To'liq yuklab olish va bepul ommaga ochish | 1–2 kun | |
| 7 | Pullik tariflar | — | avval "Adolat" markaziga xat va yozma rozilik |

### 1-bosqich. Parser va crawler

- Parser: HTML → tuzilma (qism/bo'lim/bob/modda/band). Interfeys tugmalari, "LexUZ sharhi" va
  "Oldingi tahrirga qarang" normativ matndan ajratiladi. `CHANGES_ORIGINS` va `INDEXES_ON_REF`
  metama'lumot sifatida saqlanadi.
- Crawler: ehtiyotkor ishlaydi (2 soniyada 1 so'rov, tunda). Faqat o'zgargan hujjatlar qayta
  yuklanadi (`content_hash` va tahrir sanasi bo'yicha). Ro'yxatlar ASP.NET postback orqali olinadi.
- Testlar: turli toifadagi 10–15 hujjat uchun parser snapshot testlari.

### 2-bosqich. Indekslash va qidiruv

- Chunking, embedding (ONNX), Postgres'ga yozish, HNSW va GIN indekslar.
- Gibrid qidiruv: FTS top-50 va vektor top-50 RRF bilan birlashtiriladi, keyin hujjat turi va
  holati bo'yicha filtrlanadi.
- **Baholash to'plami:** 50–100 ta real savol va ularga kutilgan moddalar. Recall@10 o'lchanadi va
  har bir o'zgarishdan keyin qayta ishga tushiriladi.

### 3–5-bosqichlar

- MCP server: FastMCP, Streamable HTTP. MCP Inspector va Claude Code bilan sinaladi.
- OAuth va kirish 7-bo'limda yozilganidek. claude.ai va ChatGPT konnektorlari bilan sinaladi.
- Deploy: Docker Compose (`caddy`, `app`, `worker`, `postgres`). Har kuni `pg_dump` bilan zaxira
  nusxa (Hetzner Storage Box), healthcheck, xatolik bo'lsa Telegram orqali xabar.

### Keyingi bosqichlar

- O'zbek (kirill) va rus tillari. Kirill↔lotin transliteratsiya qidiruvda ham foydali.
- Pullik tariflar (7-bosqich): birinchi qadam — "Adolat" markaziga xat. Yozma rozilik olingach
  tariflar va Payme/Click ulanadi (`usage_events` tayyor bo'ladi).
- Kuchliroq server: kattaroq embedding modeli, reranker (masalan `bge-reranker-v2-m3`).
- Mahalliy hokimiyat qarorlari, xalqaro shartnomalar, sud amaliyoti (Oliy sud Plenumi qarorlari).
- Hujjatlar orasidagi bog'lanishlar ("bu moddaga qaysi hujjat o'zgartirish kiritgan") va tahrirlar
  tarixi.

## 9. Repozitoriy tuzilmasi (taklif)

```
src/qonunshunos/
  crawler/      lex.uz'dan yuklab olish
  parser/       HTML → tuzilma
  text/         normalizatsiya, chunking
  index/        embedding, Postgres'ga yozish
  search/       gibrid qidiruv
  mcp/          MCP server, tool'lar
  auth/         OAuth 2.1, Google/Telegram, limitlar
  db/           modellar, Alembic migratsiyalar
tests/
eval/           baholash savollari va skripti
deploy/         docker-compose.yml, Caddyfile
docs/           tadqiqot, xatlar
```

## 10. Ochiq savollar

1. **Domen.** Google va Telegram kirishini sozlash uchun 4-bosqichdan oldin kerak bo'ladi.
2. **Kunlik limit bepul davrda.** Kuniga 3 ta qidiruv limiti xizmat to'liq bepul bo'lgan davrda
   ham qoladimi yoki pullik tariflar bilan birga kiritiladimi?
