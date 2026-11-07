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
| `docs/stage2-index-search.md` | 2-bosqich (indekslash, qidiruv, baholash) dizayni va ishlar tartibi |
| `docs/stage3-mcp-server.md` | 3-bosqich (MCP server, tool'lar) dizayni va ishlar tartibi |
| `docs/stage4-auth-limits.md` | 4-bosqich (OAuth, Google orqali kirish, limitlar) dizayni va ishlar tartibi |
| `docs/stage2-experiments.md` | Qidiruv tajribalari jurnali: raqamlar, xulosalar (portfolio uchun ham) |
| `docs/adolat-markazi-xat.md` | "Adolat" markaziga xat loyihasi |

## Asosiy qarorlar

- Hozircha xizmat to'liq bepul. Har bir javobda lex.uz'dagi asl hujjatga havola beriladi.
- Pullik tariflar va boshqa daromad manbalari faqat "Adolat" markazining yozma roziligidan keyin
  yoqiladi. Xat to'lov bosqichi boshlanganda yuboriladi.
- Faqat amaldagi tahrir indekslanadi. Kuchini yo'qotgan hujjatlarning faqat rekvizitlari saqlanadi.
- Stek: Python 3.12+, uv, MCP Python SDK (FastMCP), PostgreSQL 16 + pgvector,
  `multilingual-e5-small` (ONNX, int8).
- Joylashuv: xizmat `myserver`da (`ssh myserver`, Hetzner, systemd + nginx). Og'ir bir martalik
  ishlar (to'liq yuklab olish, embedding) `home`da (`ssh home`, Tailscale): natija SSH tunnel orqali
  to'g'ridan-to'g'ri `myserver` bazasiga yoziladi. Docker ishlatilmaydi.
- Mahalliy baza (Mac): Homebrew `postgresql@17` + `pgvector`, port 5433 (`.env.example`).
  Domen: `qonunshunos.muzaffar.zip`. DNS'ni Spaceship emas, Cloudflare boshqaradi: A yozuvi
  Cloudflare'da, proksisiz ("DNS only"), Spaceship'dagi yozuvlar ishlatilmaydi.
  Serverlarda o'zgarish qilishdan oldin foydalanuvchidan so'ra.
- Bepul davr limitlari: kuniga 30 ta qidiruv, 200 ta boshqa chaqiruv, daqiqasiga 10 ta.

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

Bosqichlar holati `PLAN.md`ning 8-bo'limida. 1–4-bosqichlar bajarildi (har birining hujjatida
"Natija" bo'limi bor, tajribalar `docs/stage2-experiments.md`da). 4-bosqich
(`docs/stage4-auth-limits.md`): OAuth 2.1, Google orqali kirish (Telegram keyinroq), limitlar,
admin CLI. Claude Code, claude.ai va ChatGPT production'da sinaldi. Xizmat
`https://qonunshunos.muzaffar.zip`da ishlayapti (namunaviy korpus). Keyingisi 5-bosqich: zaxira
nusxa, monitoring, kunlik yangilash, `auth-cleanup` timer'i.

CLI: `uv run qonunshunos fetch|parse|crawl-sample|crawl|listing|db-migrate|index|search|eval|serve|tool|user|auth-cleanup`
(`--data-dir`, standart `./data`). `serve` standart holatda OAuth talab qiladi: mahalliy
ishlab chiqishda `.env`da `QONUNSHUNOS_DEV_LOGIN=1` yoki `--no-auth` (faqat loopback'da). Mahalliy
OAuth uchun manzil `http://localhost:8000` (`127.0.0.1` emas: Google redirect shunday yozilgan).
LLM (OpenAI) faqat `qonunshunos.llm.OpenAIChat` orqali ishlatiladi: u bepul kunlik limitni
`data/llm_usage.json` bo'yicha nazorat qiladi.

## Server (`myserver`)

- Ilova `/home/deploy/qonunshunos`da, `qonunshunos.service`, `127.0.0.1:8100`. nginx sayti
  `deploy/nginx-qonunshunos.conf`. Server `.env` git'ga qo'shilmaydi va sinxronlanmaydi.
- Yangilash: `deploy/deploy.sh` (sudo kerak emas). Root talab qiladigan ishlar
  `deploy/root-setup.sh`da, uni foydalanuvchi o'zi ishga tushiradi:
  `ssh -t myserver 'sudo bash …'`. Sudo parolini hech qachon ishlatma.
- Sayt Cloudflare proksisi ortida ("Full (strict)", `*.muzaffar.zip` Origin sertifikati).
  UFW 80/443 portlarni faqat Cloudflare'ga ochgan, shuning uchun Let's Encrypt ishlamaydi.
- pgvector 0.8.7 manba kodidan yig'ilgan. PGDG paketi umumiy PostgreSQL'ni yangilab yuborardi.
- Ko'p yangi SSH ulanishdan keyin server ulanishni bir muddat rad etadi: bitta umumiy ulanish
  (ControlMaster) ishlat.
