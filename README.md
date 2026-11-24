# Nizom

O'zbekcha | [English](README.en.md)

O'zbekiston qonunchiligi bo'yicha remote MCP server. AI yordamchi (Claude, ChatGPT, Cursor va
boshqalar) foydalanuvchi savoliga mos moddani [lex.uz](https://lex.uz)dagi amaldagi matndan
topadi, o'qiydi va javobda moddaga aniq havola beradi.

- **Manzil:** `https://nizom.org/mcp` (Streamable HTTP, kirish Google orqali)
- **Narx:** bepul. Kuniga 30 ta qidiruv va 200 ta boshqa so'rov, daqiqasiga 10 ta.
- **Korpus:** 15 810 ta amaldagi hujjat (o'zbek tili, lotin yozuvi): Konstitutsiya, kodekslar,
  qonunlar, Prezident farmon va qarorlari, Vazirlar Mahkamasi qarorlari, idoralar buyruqlari.
  491 947 ta bo'lak, har kecha lex.uz'dan yangilanadi.

## Ulanish

| Mijoz | Qanday |
|---|---|
| claude.ai / Claude Desktop | Settings → Connectors → Add custom connector → `https://nizom.org/mcp` |
| ChatGPT | Settings → Apps & Connectors → Advanced settings → Developer mode → yangi konnektor |
| Claude Code | `claude mcp add --transport http nizom https://nizom.org/mcp`, keyin `/mcp` |
| Cursor va boshqalar | "remote MCP server (Streamable HTTP)" sifatida shu manzil |

## Tool'lar

| Tool | Vazifasi |
|---|---|
| `search_law` | Gibrid qidiruv: savol va AI yozgan rasmiy iboralar (`alt_queries`) bo'yicha eng mos 8 ta modda |
| `get_article` | Bitta modda yoki bandning to'liq matni, holati va oxirgi o'zgarishlari |
| `get_document` | Hujjat rekvizitlari va mundarijasi |
| `get_section` | Bob yoki bo'limning matni |
| `find_document` | Hujjatni nomi, raqami yoki turi bo'yicha topish |
| `list_codes` | Amaldagi kodekslar ro'yxati |

Har bir javobda lex.uz havolasi bor. Qidiruv natijasi ≈1 100 token, sahifa ≈2 500 tokendan oshmaydi.

## Qidiruv qanday ishlaydi

```
savol + alt_queries ─┬─ FTS (PostgreSQL): normalizatsiya → lemma → stemming → IDF og'irligi ─┐
                     └─ vektor: fine-tune qilingan e5-small (ONNX int8) → pgvector HNSW ──────┴─ RRF
   → top 30 modda → fine-tune qilingan cross-encoder (reranker) → 8 ta modda
```

- O'zbek tili uchun tayyor stemmer yo'q, shuning uchun o'zimiz yozdik (kelishik → egalik →
  ko'plik). Unga uzmorph yordamida tuzilgan 9 081 ta otning lemma jadvali qo'shildi.
- Embedding modeli `multilingual-e5-small` va reranker `mmarco-mMiniLMv2-L12` o'zbekcha yuridik
  "savol → modda" juftliklarida qo'shimcha o'qitildi (pastda).
- Server GPU'siz ishlaydi (Hetzner, 2 yadro): bitta qidiruv 2–3 s, asosiy vaqt reranker'da.

## Natijalar

Metrika: **Recall@10**, ya'ni to'g'ri modda birinchi 10 ta natija ichida bo'lgan savollar ulushi.
R@1 — to'g'ri modda birinchi o'rinda. O'lchovlar butun korpusda, xizmatdagi kod bilan, AI qayta
yozgan savollar (`alt_queries`) bilan o'tkazildi. Batafsil: [docs/stage2-experiments.md](docs/stage2-experiments.md).

### Fine-tune'dan oldin va keyin

To'plam: GPT-5.4 butun korpusdan yozgan 208 ta aniq savol (`eval/questions_llm_full.yaml`).

| Qadam | R@1 | R@5 | R@10 | MRR |
|---|---:|---:|---:|---:|
| Boshlang'ich: asl e5-small, reranker'siz | 0,245 | 0,562 | 0,668 | 0,375 |
| + asl reranker (top 20) | 0,394 | 0,649 | 0,716 | 0,502 |
| Fine-tune qilingan e5-small, reranker'siz | 0,389 | 0,697 | 0,793 | 0,515 |
| Fine-tune qilingan e5-small + asl reranker | 0,462 | 0,764 | 0,846 | 0,586 |
| **+ lemma, yangi birlashtirish, fine-tune qilingan reranker (top 30)** | **0,538** | **0,822** | **0,875** | **0,655** |

Butun yo'l: R@10 0,668 → 0,875, R@1 ikki barobardan ko'p (0,245 → 0,538).

Faqat vektor qidiruvida farq yanada katta: butun korpusda R@10 0,25 → 0,66. 72 ming bo'lakli
nomzodlar pool'ida asl model 0,385, fine-tune qilingani 0,760.

**O'qitish.** 1 849 ta "savol → modda" juftligi (GPT-5.4 yozgan, iqtibos bilan tekshirilgan;
baholash hujjatlari chiqarib tashlangan). In-batch negatives, 6 epoch, lr 3e-5. Reranker esa
fine-tune qilingan e5 topgan hard negative'lar bilan o'qitildi (guruhda 1 to'g'ri + 15 noto'g'ri).
Ijaradagi GPU'da (RunPod) bitta o'qitish ≈40 s, butun korpusni qayta embedding qilish ≈5,5 daqiqa.
Barcha GPU tajribalari ≈3 $ turdi.

Kuzatuvlar:
- Juftliklar soni 753 dan 1 849 gacha oshganda natija deyarli o'zgarmadi (0,774 → 0,793).
  Ko'proq epoch foyda berdi (2 epoch 0,793, 6 epoch 0,837, pool'da).
- Seed shovqini katta: bir xil sozlamada R@10 0,808–0,841. Har bir qaror bir nechta run bilan tekshirildi.
- int8 kvantlash sifatni pasaytirmadi (pool'da 0,837 va 0,837), shuning uchun serverga int8 qo'yildi.

### Mustaqil tekshiruv

Sozlamalar yuqoridagi 208 savolda tanlangani uchun natija optimistik bo'lishi mumkin edi. Shuning
uchun yana uchta to'plamda o'lchandi:

| To'plam | Savol | R@1 | R@10, qat'iy | R@10, hakam bilan |
|---|---:|---:|---:|---:|
| GPT-5.4 savollari, `test` qismi (sozlashda ishlatilmagan) | 104 | 0,529 | 0,856 | — |
| "Ko'r" savollar: moddani ko'rmay yozilgan, javoblar korpusdan qo'lda topilgan | 120 | 0,408 | 0,800 | 0,917 |
| [advice.uz](https://advice.uz): odamlar bergan, yurist javob bergan savollar | 225 | 0,493 | 0,876 | 0,964 |

- **Qat'iy** — faqat oldindan belgilangan javoblar hisoblanadi. **Hakam bilan** — top-10 dagi
  boshqa to'g'ri moddalar ham hisoblanadi (LLM hakam topadi, har biri iqtibos bilan tekshirilgan).
  Haqiqiy qiymat shu ikki raqam orasida.
- Uchala to'plam bir xil manzarani beradi. Haqiqiy savollarda (advice.uz) natija LLM
  savollaridagidan past emas.
- Kontekstsiz, noaniq savollarda ("Shartnoma qancha muddatga tuziladi?") R@10 0,58–0,59. Bunday
  holda AI foydalanuvchidan aniqlashtirishi kerak.

### Claude Code bilan uchdan-uchgacha sinov

Claude Code'ga faqat Nizom berildi (veb-qidiruvsiz), 10 ta savol:

| Mezon | Natija |
|---|---|
| Kutilgan modda `get_article` bilan o'qildi | 10/10 |
| Javobdagi havolalar haqiqiy moddaga olib boradi | 34/35 |
| "Yuridik maslahat emas" ogohlantirishi | 10/10 |
| Bitta savolga tool chaqiruvi | 3–8 (o'rtacha 5) |

## Stek

Python 3.12, [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) (FastMCP),
PostgreSQL 16 + pgvector (halfvec, HNSW), onnxruntime (int8), OAuth 2.1 + Google.
Xizmat: bitta Hetzner server, systemd + nginx, Cloudflare. Har kecha yangilash, zaxira nusxa va
Telegram'ga xabar. Docker yo'q.

## Ishlab chiqish

```sh
uv sync
uv run nizom --help
uv run ruff format . && uv run ruff check . && uv run pytest
```

Testlar tarmoqqa chiqmaydi: `tests/fixtures/`dagi qisqartirilgan haqiqiy sahifalar ishlatiladi.
Mahalliy server: `.env.example` asosida `.env`, keyin `uv run nizom serve --no-auth`.
Fine-tune qilingan model fayllari repoga kiritilmagan.

Hujjatlar: [PLAN.md](PLAN.md) (qarorlar va bosqichlar), [docs/](docs/) (har bir bosqich dizayni
va natijasi, lex.uz tadqiqoti).

## Huquqiy holat

Rasmiy hujjatlar (qonunlar, qarorlar) mualliflik huquqi obyekti emas ("Mualliflik huquqi va
turdosh huquqlar to'g'risida"gi Qonun, [8-modda](https://lex.uz/docs/-1022944#-1023047)). Xizmat
bepul va har bir javobda lex.uz'ga havola beradi. Bu norasmiy loyiha: lex.uz, "Adolat" milliy
huquqiy axborot markazi va davlat organlariga aloqasi yo'q. Javoblar umumiy ma'lumot, yuridik
maslahat emas.

## Litsenziya

Kod: [MIT](LICENSE).
