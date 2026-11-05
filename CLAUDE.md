# CLAUDE.md

## Loyiha

**Qonunshunos** (ishchi nom) — O'zbekiston Respublikasi qonunchiligiga oid savollarga javob
topishda yordam beradigan remote MCP server. Manba — lex.uz (o'zbek tili, lotin yozuvi).
Dasturlash tili — Python.

## Muloqot

- Foydalanuvchi bilan o'zbek tilida (lotin yozuvi) gaplash. Repodagi hujjatlar ham o'zbekcha.
- Kod, identifikatorlar, kod izohlari va commit xabarlari inglizcha yoziladi.

## Asosiy hujjatlar

| Fayl | Mazmuni |
|---|---|
| `PLAN.md` | Qarorlar, arxitektura, bosqichlar va ularning holati. Bosqich tugaganda 8-bo'limdagi jadvalni yangila |
| `docs/research/lexuz.md` | lex.uz tadqiqoti: URL'lar, endpoint'lar, HTML tuzilishi, hajm, huquqiy holat |
| `docs/stage1-parser-crawler.md` | 1-bosqich (parser + crawler) dizayni va ishlar tartibi |
| `docs/adolat-markazi-xat.md` | "Adolat" markaziga xat loyihasi |

## Asosiy qarorlar

- Hozircha xizmat to'liq bepul. Har bir javobda lex.uz'dagi asl hujjatga havola beriladi.
- Pullik tariflar va boshqa daromad manbalari faqat "Adolat" markazining yozma roziligidan keyin
  yoqiladi. Xat to'lov bosqichi boshlanganda yuboriladi.
- Faqat amaldagi tahrir indekslanadi. Kuchini yo'qotgan hujjatlarning faqat rekvizitlari saqlanadi.
- Stek: Python 3.12+, uv, MCP Python SDK (FastMCP), PostgreSQL + pgvector,
  `multilingual-e5-small` (ONNX, int8), Docker Compose + Caddy, Hetzner (4 GB RAM / 2 vCPU).

## lex.uz bilan ishlash

- So'rovlar orasida kamida 2 soniya, parallel so'rov yo'q. User-Agent: `QonunshunosBot/0.1`,
  unga shaxsiy ma'lumot (email) qo'yilmaydi.
- Lotin versiya: `https://lex.uz/docs/-{id}` (manfiy ID).
- Yuklab olingan sahifalar `data/`ga saqlanadi va git'ga qo'shilmaydi.
- Testlar tarmoqqa chiqmaydi, `tests/fixtures/`dagi qisqartirilgan haqiqiy sahifalar ishlatiladi.

## Kod

- Tuzilma: `src/qonunshunos/`, testlar `tests/`da.
- Commitdan oldin: `uv run ruff format .`, `uv run ruff check .`, `uv run pytest`.
- Commitlar kichik va mantiqiy bo'lsin.

## Joriy holat

Bosqichlar holati `PLAN.md`ning 8-bo'limida. 1-bosqich bajarildi
(`docs/stage1-parser-crawler.md`, "Natija"). Keyingi ish — 2-bosqich: indekslash, gibrid qidiruv,
baholash to'plami.

CLI: `uv run qonunshunos fetch|parse|crawl-sample` (`--data-dir`, standart `./data`).
