# Uzbek Law MCP — loyiha rejasi

O'zbekiston Respublikasi qonunchiligiga oid savollarga javob topishda yordam beradigan,
pullik xizmat sifatida taqdim etiladigan masofaviy (remote) MCP server.

## 1. Qabul qilingan qarorlar

| Mavzu | Qaror |
|---|---|
| Manba | lex.uz (Milliy qonunchilik ma'lumotlari bazasi), mahalliy bazaga yuklab olinadi va indekslanadi |
| Qamrov | Konstitutsiya, kodekslar, qonunlar + qonun osti hujjatlari (Prezident farmon/qarorlari, Vazirlar Mahkamasi qarorlari va h.k.) |
| Til | Hozircha o'zbek (lotin). Keyin: o'zbek (kirill), rus |
| Qidiruv | Gibrid: to'liq matnli (kalit so'z) + semantik (embedding), natijalar RRF bilan birlashtiriladi |
| Embedding | Hetzner serverning o'zida, ochiq ko'p tilli model |
| Tahrirlar | Faqat amaldagi tahrir + "kuchini yo'qotgan" belgisi |
| Yangilash | Har kuni tunda avtomatik |
| Stek | Python: MCP Python SDK (FastMCP) + Starlette/FastAPI |
| Joylashuv | Hetzner, 4 GB RAM / 2 vCPU (keyin kuchliroq server) |
| Transport | Streamable HTTP (remote MCP) |
| Mijozlar | claude.ai, Claude Desktop, Claude Code, ChatGPT, Cursor — OAuth 2.1 orqali |
| To'lov | Hozircha yo'q. Lekin foydalanuvchi, limit va foydalanish statistikasi boshidan yoziladi (keyin Payme/Click ulash oson bo'lishi uchun) |

## 2. Arxitektura

```
                 ┌──────────────────────── Hetzner (Docker Compose) ───────────────────────┐
 MCP mijoz ──TLS──► Caddy (HTTPS, avtomatik sertifikat)                                      │
 (claude.ai,     │    │                                                                     │
  ChatGPT, ...)  │    ├─► app: MCP server (/mcp) + OAuth server (/authorize, /token, ...)   │
                 │    │        │  search_law, get_article, ...                               │
                 │    │        ▼                                                             │
                 │    │   PostgreSQL 16 + pgvector + pg_trgm                                 │
                 │    │        ▲                                                             │
                 │    └─ worker: kunlik cron → lex.uz crawler → parser → chunk → embedding  │
                 └──────────────────────────────────────────────────────────────────────────┘
```

### Nima uchun shunday?

- **PostgreSQL + pgvector** — bitta baza: hujjatlar, FTS indeksi, vektorlar, foydalanuvchilar,
  OAuth tokenlar, statistika. Ko'p foydalanuvchili rejimga mos, zaxira nusxa olish oson.
- **Embedding modeli: `intfloat/multilingual-e5-small`** (ONNX, int8 kvantlangan, `fastembed`
  yoki `onnxruntime` orqali). ~120M parametr, ~250 MB RAM, 384 o'lchamli vektor.
  4 GB serverga sig'adi. Kuchliroq serverga o'tganda `bge-m3` yoki `multilingual-e5-base`'ga
  almashtiriladi (model nomi va o'lchami konfiguratsiyada, qayta indekslash skripti bilan).
- **To'liq matnli qidiruv**: PostgreSQL'da o'zbek tili uchun stemmer yo'q, shuning uchun
  `simple` konfiguratsiya + o'zimizning yengil normalizatsiya (pastki registr, apostroflarni
  birxillashtirish, oddiy qo'shimchalarni kesish) + `pg_trgm` (xatoli yozilishlar uchun).

### 4 GB server cheklovlari

- Boshlang'ich to'liq indekslash (o'n minglab hujjat, millionlab bo'lak) 2 vCPU'da ko'p soat/kun
  olishi mumkin. Variant: birinchi indekslashni kuchliroq mashinada (yoki vaqtincha katta
  Hetzner instansiyasida) bajarib, bazani serverga ko'chirish. Kunlik yangilanishlar kichik.
- HNSW indeksi RAM talab qiladi; vektorlar `halfvec` (float16) bilan saqlanadi.
- Postgres: `shared_buffers≈768MB`, app + model ≈ 1 GB, qolgani OS kesh uchun.

## 3. Ma'lumotlar modeli (soddalashtirilgan)

```
documents   id, lex_id, title, doc_type (kodeks/qonun/farmon/qaror/...), number,
            adopted_at, issuing_body, status (amalda / kuchini yo'qotgan),
            url, lang, content_hash, fetched_at, updated_at
sections    id, document_id, parent_id, kind (bo'lim/bob/paragraf/modda/band),
            number, title, text, path ("II bo'lim > 5-bob > 37-modda"), ord
chunks      id, section_id, document_id, text, text_norm, tsv (tsvector),
            embedding halfvec(384)
users, oauth_clients, oauth_tokens, api_usage (user_id, tool, ts, latency, tokens)
```

Asosiy birlik — **modda**. Uzun moddalar band/qism bo'yicha bo'linadi; har bir bo'lakka
kontekst sarlavhasi qo'shiladi ("Mehnat kodeksi, 37-modda. Mehnat shartnomasini bekor qilish").

## 4. MCP interfeysi

### Tools

| Tool | Vazifasi |
|---|---|
| `search_law(query, doc_types?, in_force_only=true, limit=10)` | Gibrid qidiruv. Natija: hujjat nomi, modda raqami va sarlavhasi, parcha, lex.uz havolasi |
| `get_article(document, article)` | Muayyan moddaning to'liq matni (masalan: "Mehnat kodeksi", "131") |
| `get_document(document_id)` | Hujjat metama'lumotlari + mundarija (bo'lim/bob/moddalar ro'yxati) |
| `get_section(document_id, path)` | Bob/bo'lim matni (uzun bo'lsa sahifalab) |
| `find_document(title_or_number, doc_type?, year?)` | Hujjatni nomi/raqami bo'yicha topish ("PF-60", "VMQ 1029") |
| `list_codes()` | Barcha amaldagi kodekslar ro'yxati |

Tamoyillar: har bir javobda **manba havolasi** (lex.uz URL) va hujjat holati bo'ladi;
javoblar ixcham (token tejash), uzun matn sahifalanadi.

### Prompts

- `yuridik_savol` — savolga javob berish tartibi: avval qidirish, moddalarni o'qish, javobda
  aniq moddalarga havola berish, "bu yuridik maslahat emas" ogohlantirishi.

### Resources

- `lex://document/{id}`, `lex://document/{id}/article/{n}`

## 5. Bosqichlar

### 0-bosqich. Tadqiqot (1–2 kun)
- lex.uz tuzilishini o'rganish: hujjat ID'lari, URL formatlari, lotin versiyasini olish,
  hujjat turlari ro'yxati, "o'zgarishlar" sahifasi, sitemap/RSS bormi.
- `robots.txt` va foydalanish shartlarini tekshirish. Iloji bo'lsa Adliya vazirligi /
  lex.uz ma'muriyatidan ruxsat yoki rasmiy API so'rash (pullik xizmat bo'lgani uchun muhim).
- Hujjatlar sonini va hajmini baholash.

### 1-bosqich. Crawler va parser (1 hafta)
- Ehtiyotkor crawler: so'rovlar orasida pauza, `If-Modified-Since`/hash bilan faqat o'zgarganini olish.
- HTML → tuzilma (bo'lim/bob/modda/band) parser. O'zbekcha apostroflar (`oʻ o' o‘ o'` → bitta shakl).
- Testlar: 10–15 xil turdagi hujjat uchun parser snapshot testlari.

### 2-bosqich. Indekslash va qidiruv (1 hafta)
- Chunking, embedding (ONNX), Postgres'ga yozish, HNSW + GIN indekslar.
- Gibrid qidiruv: FTS top-50 + vektor top-50 → RRF → hujjat turi/holati bo'yicha filtr.
- **Baholash to'plami**: 50–100 ta real savol va kutilgan moddalar. Recall@10 o'lchanadi,
  har bir o'zgarishdan keyin qayta ishga tushiriladi.

### 3-bosqich. MCP server (3–4 kun)
- FastMCP, Streamable HTTP, yuqoridagi tool'lar.
- Lokal sinov: MCP Inspector va Claude Code bilan (vaqtincha auth'siz yoki dev-token).

### 4-bosqich. OAuth va foydalanuvchilar (1 hafta)
- OAuth 2.1 avtorizatsiya serveri: Dynamic Client Registration, PKCE,
  `/.well-known/oauth-protected-resource` va `oauth-authorization-server` metama'lumotlari.
- Kirish: email (magic link) va/yoki Google login. Oddiy ro'yxatdan o'tish sahifasi.
- Har foydalanuvchiga limit (masalan kuniga N so'rov), `api_usage` jadvaliga yozish.
- claude.ai va ChatGPT konnektorlari bilan sinash.

### 5-bosqich. Deploy (2–3 kun)
- Docker Compose: `caddy`, `app`, `worker`, `postgres`.
- Domen + HTTPS, kunlik `pg_dump` zaxira (Hetzner Storage Box), loglar, oddiy monitoring
  (healthcheck + uptime).
- Kunlik yangilash cron'i va xatolik haqida xabarnoma (Telegram bot).

### Keyingi bosqichlar
- O'zbek (kirill) va rus tillari (kirill↔lotin transliteratsiya qidiruvda ham foydali).
- To'lov: tariflar, Payme/Click integratsiyasi (`api_usage` tayyor bo'ladi).
- Kuchliroq server → kattaroq embedding modeli, reranker (masalan `bge-reranker-v2-m3`).
- Hujjatlar orasidagi havolalar ("ushbu moddaga o'zgartirish kiritgan hujjat"), tahrirlar tarixi.
- Sud amaliyoti, Oliy sud Plenumi qarorlari.

## 6. Repozitoriy tuzilmasi (taklif)

```
src/uzlaw/
  crawler/      lex.uz yuklab olish
  parser/       HTML → tuzilma
  text/         normalizatsiya, chunking
  index/        embedding, Postgres'ga yozish
  search/       gibrid qidiruv
  mcp/          MCP server, tool'lar
  auth/         OAuth 2.1, foydalanuvchilar, limitlar
  db/           modellar, Alembic migratsiyalar
tests/
eval/           baholash savollari va skripti
deploy/         docker-compose.yml, Caddyfile
```

## 7. Ochiq savollar

1. Domen nomi va loyiha/brend nomi.
2. lex.uz ma'lumotlaridan tijoriy foydalanishga ruxsat (0-bosqichda aniqlanadi).
3. Bepul tarifdagi kunlik limit qancha bo'lsin?
4. Kirish usuli: faqat email, Google, yoki Telegram orqali ham?
