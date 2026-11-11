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
| `docs/stage5-ops.md` | 5-bosqich (zaxira nusxa, monitoring, kunlik yangilash) dizayni va ishlar tartibi |
| `docs/stage6-full-crawl.md` | 6-bosqich (to'liq yuklab olish, ommaga ochish) dizayni va ishlar tartibi |
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
  ishlar (embedding) `home`da (`ssh home`, Tailscale): natija SSH tunnel orqali to'g'ridan-to'g'ri
  `myserver` bazasiga yoziladi. `home` — foydalanuvchining ishxonadagi kompyuteri, IP'si butun
  ishxona bilan umumiy: lex.uz'ga ko'p so'rov (to'liq yuklab olish) `myserver`dan yuboriladi.
  Docker ishlatilmaydi.
- Mahalliy baza (Mac): Homebrew `postgresql@17` + `pgvector`, port 5433 (`.env.example`).
  Domen: `qonunshunos.muzaffar.zip`. DNS'ni Spaceship emas, Cloudflare boshqaradi: A yozuvi
  Cloudflare'da, proksi yoqilgan (2026-11-06 dan), Spaceship'dagi yozuvlar ishlatilmaydi.
  Serverlarda o'zgarish qilishdan oldin foydalanuvchidan so'ra.
- Bepul davr limitlari: kuniga 30 ta qidiruv, 200 ta boshqa chaqiruv, daqiqasiga 10 ta.

## lex.uz bilan ishlash

- So'rovlar orasida kamida 2 soniya, parallel so'rov yo'q. User-Agent: `QonunshunosBot/0.1`,
  unga shaxsiy ma'lumot (email) qo'yilmaydi.
- Lotin versiya: `https://lex.uz/docs/-{id}` (odatda manfiy ID; 402 ta lotin hujjatda ID musbat).
- Yuklab olingan sahifalar `data/`ga saqlanadi va git'ga qo'shilmaydi.
- Testlar tarmoqqa chiqmaydi, `tests/fixtures/`dagi qisqartirilgan haqiqiy sahifalar ishlatiladi.

## Kod

- Tuzilma: `src/qonunshunos/`, testlar `tests/`da.
- Commitdan oldin: `uv run ruff format .`, `uv run ruff check .`, `uv run pytest`.
- Commitlar kichik va mantiqiy bo'lsin.

## Joriy holat

Bosqichlar holati `PLAN.md`ning 8-bo'limida. 1–5-bosqichlar bajarildi (har birining hujjatida
"Natija" bo'limi bor, tajribalar `docs/stage2-experiments.md`da). Xizmat
`https://qonunshunos.muzaffar.zip`da ishlayapti (to'liq korpus). Har kecha
`qonunshunos update` lex.uz'dan yangilaydi, zaxira `home`ga ko'chiriladi, xatolar va ertalabki
hisobot Telegram'ga (@qonunshunosbot) keladi (`docs/stage5-ops.md`). 6-bosqich jarayonda
(`docs/stage6-full-crawl.md`): 15 810 ta amaldagi lotin hujjat yuklab olindi, parser v2 bilan
parse qilindi va server bazasiga indekslandi (491 947 bo'lak, HNSW qurilgan, tungi update timer'i
yoqilgan). To'liq bazada qidiruv sifati yetarli emas: aniq savollarda gibrid R@10 0,64, maqsad
0,85; oflayn sinovda yengil reranker 0,755 berdi (`docs/stage2-experiments.md` 6d, "Qisqacha"
jadvali). Ommaga ochish shu tuzatilguncha kechiktirilgan. Keyingi tanlov: A) yengil reranker'ni
xizmatga qo'yish (int8 ONNX, serverda tezlik), B) tekshirilgan "savol → modda" to'plamida
embedding va reranker'ni qo'shimcha o'qitish.

Baholash: `eval/questions_llm_full.yaml` (300 savol, `aniq`/`noaniq` teglari, javoblar
tekshirilgan) asosiy to'plam; natijalar `eval/results/`da. Server bazasiga tegadigan o'lchovlarni
foydalanuvchi `bash scripts/with_server_db.sh <buyruq>` bilan ishga tushiradi (auto mode
tunnelni ochishga ruxsat bermaydi). Oflayn tajribalar: `scripts/fusion_lab.py`,
`scripts/rerank_lab.py` (`data/eval/`dagi nomzodlar va matnlar ustida, `--group bench`).
LLM `judge` natijasini iqtibosli tekshiruvsiz ishlatma (6d).

CLI: `uv run qonunshunos fetch|parse [--all]|crawl-sample|crawl|listing|scope|crawl-full|db-migrate|index|search|eval|serve|tool|user|auth-cleanup|update|report|notify`
(`--data-dir`, standart `./data`). `serve` standart holatda OAuth talab qiladi: mahalliy
ishlab chiqishda `.env`da `QONUNSHUNOS_DEV_LOGIN=1` yoki `--no-auth` (faqat loopback'da). Mahalliy
OAuth uchun manzil `http://localhost:8000` (`127.0.0.1` emas: Google redirect shunday yozilgan).
LLM (OpenAI) faqat `qonunshunos.llm.OpenAIChat` orqali ishlatiladi: u bepul kunlik limitni
`data/llm_usage.json` bo'yicha nazorat qiladi.

## Server (`myserver`)

- Ilova `/home/deploy/qonunshunos`da, `qonunshunos.service`, `127.0.0.1:8100`. nginx sayti
  `deploy/nginx-qonunshunos.conf`. Server `.env` git'ga qo'shilmaydi va sinxronlanmaydi.
- Yangilash: `bash deploy/deploy.sh` (sudo kerak emas, `home`da server manzilini `watch.env`dan
  oladi). Auto mode deploy'ni to'xtatadi: uni foydalanuvchi oddiy terminalda ishga tushiradi.
  Root talab qiladigan ishlar `deploy/root-setup.sh`da, uni ham foydalanuvchi o'zi ishga tushiradi:
  `ssh -t myserver 'sudo bash …'`. Sudo parolini hech qachon ishlatma.
- Sayt Cloudflare proksisi ortida ("Full (strict)", `*.muzaffar.zip` Origin sertifikati).
  UFW 80/443 portlarni faqat Cloudflare'ga ochgan, shuning uchun Let's Encrypt ishlamaydi.
- pgvector 0.8.7 manba kodidan yig'ilgan. PGDG paketi umumiy PostgreSQL'ni yangilab yuborardi.
- Ko'p yangi SSH ulanishdan keyin server ulanishni bir muddat rad etadi: bitta umumiy ulanish
  (ControlMaster) ishlat.
- Tungi timer'lar `deploy/systemd/`da, `root-setup.sh` 6-qadami o'rnatadi (unit o'zgarsa qayta
  ishga tushiriladi). `home`dagi user timer'lar: `deploy/home/install.sh` (Mac'dan).
  Telegram token va chat ID: server `.env` va `home`dagi `~/.config/qonunshunos/watch.env`.
