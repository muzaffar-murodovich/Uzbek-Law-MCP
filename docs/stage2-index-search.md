# 2-bosqich: indekslash, gibrid qidiruv, baholash to'plami

Holat (2026-11-06): ✅ bajarildi. Tajribalar va raqamlar: [stage2-experiments.md](stage2-experiments.md). Tegishli hujjatlar: [PLAN.md](../PLAN.md) (4–6-bo'limlar),
[1-bosqich](stage1-parser-crawler.md).

## Maqsad

1-bosqichdagi `data/parsed/*.json`ni PostgreSQL'ga yozish, bo'laklarga bo'lish, embedding hisoblash
va gibrid qidiruvni (FTS + vektor, RRF) qurish. Qidiruv sifati baholash to'plami bilan o'lchanadi.
Har bir o'zgarishdan keyin Recall@10 qayta hisoblanadi. Bu bosqichda MCP server yo'q, faqat
kutubxona va CLI bor. MCP server 3-bosqichda shu kutubxona ustiga quriladi.

## Tayyor bo'lish mezonlari

- `qonunshunos db-migrate` bazani yaratadi yoki yangilaydi (PostgreSQL 16 + pgvector + pg_trgm).
- `qonunshunos index [<id>...]` parse qilingan hujjatlarni bazaga yozadi. Agar hujjat
  o'zgarmagan bo'lsa (`content_hash` bir xil), qayta ishlamaydi.
- `qonunshunos search "<savol>"` gibrid qidiruv natijalarini chiqaradi: hujjat, modda, yo'l,
  havola, ball.
- `qonunshunos eval` baholash to'plamini ishga tushiradi va hisobot beradi: Recall@5,
  Recall@10, MRR. Hisobotda FTS, vektor va gibrid alohida ko'rsatiladi.
- Baholash to'plamida 80–100 ta savol bo'ladi. Gibrid qidiruvda Recall@10 ≥ 0,80 bo'lishi kerak.
  Bu dastlabki mo'ljal, birinchi o'lchovdan keyin aniqlashtiriladi.
- Qidiruv kechikishi (embedding + SQL) bitta so'rov uchun 300 ms'dan oshmaydi. Bu 2 vCPU'li
  serverga mo'ljallangan.
- Testlar bazasiz va tarmoqsiz o'tadi. Baza kerak bo'lgan testlar alohida belgilanadi
  (`-m db`) va faqat `QONUNSHUNOS_TEST_DSN` berilganda ishlaydi.

## Ishlar tartibi

1. ✅ Mahalliy muhit: Homebrew `postgresql@17` + `pgvector` (port 5433), DSN `.env` orqali
   beriladi. Docker ishlatilmaydi.
2. ✅ `db/`: sxema, migratsiyalar (`0001`–`0003`), `db-migrate`.
3. ✅ `text/chunk.py` (bo'lish) va `text/fts.py` (FTS normalizatsiyasi) + testlar.
4. ✅ `index/embed.py` (ONNX model) + `index/writer.py` + `index` CLI.
5. ✅ `search/` (IDF og'irlikli FTS, vektor, RRF, filtrlar) + `search` CLI.
6. ✅ `eval/`: savollar to'plamlari + `eval` CLI.
7. ✅ Sozlash va embedding modellarini solishtirish:
   [stage2-experiments.md](stage2-experiments.md).

## Natija (2026-11-06)

- Korpus: 86 ta hujjat (Konstitutsiya, 20 ta kodeks, 65 ta qonun), 16 657 ta bo'lak.
- **Gibrid R@10, AI qayta yozganda** (LLM `alt`): qo'lda yozilgan 97 ta savolda **0,91**, LLM
  yaratgan 100 ta savolda **0,88**. Mezon (≥ 0,80) bajarildi. Xom so'zlashuv savollarida esa
  0,70.
- Kechikish: bitta so'rov 20–50 ms (embedding + SQL), mezon 300 ms.
- **Model:** hozircha `multilingual-e5-small` (int8 ONNX) qoladi (2026-11-06 qarori). Sifat
  bo'yicha bge-m3 birinchi (MRR +0,1), lekin `myserver`ning 3,7 GB RAM'iga og'ir. Kuchliroq
  serverga o'tganda almashtiriladi (`--model`, `index --force`).
- Dizayndan farqlar: bo'lak chegarasi 1500/1100 belgi (token o'lchovi: ≈4,5 belgi = 1 token).
  FTS'da `ts_rank_cd` o'rniga IDF og'irligi ishlatiladi (`fts_stats`). HNSW parametrlari
  `m=32`, `ef_construction=200`. Mahalliy baza Docker'siz.
- Ochiq: farmon va qarorlar baholash to'plamida yo'q. Haqiqiy foydalanuvchi savollari
  xizmat ishga tushgach yig'iladi.

## Korpus

Namunaviy to'plam (Konstitutsiya va 20 ta kodeks, 7282 ta modda, ≈7,9 mln belgi) faqat
kodekslarni qamraydi. Odamlar esa ko'pincha qonunlar, farmonlar va qarorlarda yozilgan narsalarni
so'raydi: pensiya, soliq imtiyozlari, litsenziya, ta'til va hokazo. Bunday savollarda tizimni
sinash uchun to'plam kengaytiriladi:

- eng muhim ≈60 ta amaldagi qonun ("Qonun" shakli bo'yicha ro'yxatdan, mavzusi bo'yicha
  tanlanadi);
- ≈20 ta farmon va Vazirlar Mahkamasi qarori (nizomli, ilovali; ularning tuzilishi 1-bosqichda
  4 ta namunada sinalgan).

Bu taxminan 160 ta so'rov, ya'ni 2 soniya oraliq bilan ≈6 daqiqa. To'liq yuklab olish
(≈22 ming hujjat) 6-bosqichda `home` serverda bajariladi.

## Ma'lumotlar bazasi

Kirish — `psycopg` 3 (sinxron, pool bilan), toza SQL. ORM ishlatilmaydi: so'rovlar kam va
qidiruv SQL'ni qo'lda yozish qulayroq. Migratsiyalar — `src/qonunshunos/db/migrations/NNNN_*.sql`
fayllari va `schema_migrations` jadvali. Alembic'ning bu yerda foydasi yo'q.

```sql
documents (
  id            bigint PRIMARY KEY,        -- lex_id (manfiy, lotin)
  title, doc_type, number, adopted_at date, status, accepting_body, url,
  edition_date date, last_change_date date, content text ('html'|'pdf_only'),
  content_hash  text,                      -- parsed JSON sha256 (parser_version bilan)
  card          jsonb, meta jsonb,         -- card1 va qolgan rekvizitlar
  title_norm    text,                      -- trigram qidiruv uchun (find_document)
  indexed_at    timestamptz
)
sections (                                 -- heading'lar va unit'lar, hujjat tartibida
  id bigserial, document_id, ord int, kind, number, title, path text[],
  elem_id bigint, text text, okoz text[], changes jsonb
)
chunks (
  id bigserial, document_id, section_id, ord int,
  heading  text,                           -- kontekst sarlavhasi
  text     text,                           -- foydalanuvchiga ko'rsatiladigan matn
  tsv      tsvector,                       -- heading (A og'irlik) + text (B)
  embedding halfvec(384)
)
```

Indekslar: `chunks.tsv` uchun GIN, `chunks.embedding` uchun HNSW (`halfvec_cosine_ops`,
`m=16, ef_construction=64`), `documents.title_norm` uchun `gin_trgm_ops`.

Kuchini yo'qotgan hujjatlar: `documents`da faqat rekvizitlari saqlanadi, `sections` va `chunks`
yaratilmaydi. Faqat PDF'li hujjatlar ham shu tarzda saqlanadi va `content='pdf_only'` deb
belgilanadi.

## Bo'laklash (chunking)

- Asosiy birlik — `Unit` (modda, band, kirish, matn). Model ko'pi bilan 512 tokenni qabul qiladi.
  O'zbek lotin matnida bu taxminan 1500–1800 belgiga to'g'ri keladi. Aniq nisbat tokenizer bilan
  o'lchanadi.
- Unit ≤ 1200 belgi bo'lsa (modda va bandlarning ≈75 foizi), u bitta bo'lak bo'ladi.
- Unit uzunroq bo'lsa, xatboshi chegarasida ≈1000 belgilik bo'laklarga bo'linadi. Moddaning
  birinchi xatboshisi (odatda kirish gapi, masalan "Quyidagi sabablar…") har bir bo'lakka
  takrorlanadi, chunki bandlar ro'yxati usiz tushunarsiz qoladi. Juda uzun xatboshi gap
  chegarasida bo'linadi.
- Jadval qatorlari matnga aylantiriladi (`ustun: qiymat; ...`) va xuddi shu qoidalar bilan
  bo'linadi. Bo'laklar soni chegaralanadi: bitta unit'dan ko'pi bilan 30 ta. 51 ming belgilik
  jadvalli modda ham shu chegaraga tushadi.
- Kontekst sarlavhasi embedding'ga ham, FTS'ga ham qo'shiladi:
  `"Mehnat kodeksi. 12-bob. Mehnat shartnomasi. 161-modda. Mehnat shartnomasini ish beruvchining
  tashabbusiga ko'ra bekor qilish"`. Hujjat nomi qisqa shaklda yoziladi ("Oʻzbekiston
  Respublikasining" qo'shimchasisiz).

## Embedding

- Model: `intfloat/multilingual-e5-small`, ONNX int8 versiyasi (`Xenova/multilingual-e5-small`,
  `onnx/model_int8.onnx`, 118 MB) va `tokenizer.json`. Ishga tushirish: `onnxruntime` +
  `tokenizers` (torch kerak emas). Mean pooling va L2 normalizatsiya qilinadi. Prefikslar:
  `query: ` va `passage: `.
- Model fayllari birinchi ishga tushishda `data/models/`ga yuklanadi va sha256 bilan tekshiriladi.
  Model nomi va revision konfiguratsiyada saqlanadi. Model almashtirilganda `index --reembed`
  ishlatiladi.
- Sifat tekshiruvi: int8 va fp32 natijalari baholash to'plamida solishtiriladi. Agar farq
  sezilarli bo'lsa, `model_fp16.onnx` (235 MB) olinadi.

## FTS normalizatsiyasi

PostgreSQL'da o'zbek tili uchun stemmer yo'q. Shuning uchun matn Python'da normalizatsiya qilinadi
va `to_tsvector('simple', ...)`ga beriladi. So'rov ham aynan shu funksiyadan o'tadi.

1. `fold`: pastki registr, apostroflar bitta shaklga, `oʻ/gʻ` → `o'/g'` → `o`, `g` (apostrofsiz).
   Shunda "ko'ra", "koʻra" va "kora" bir xil bo'ladi.
2. To'xtatuvchi so'zlar: "va", "yoki", "bilan", "uchun", "boʻyicha", "hamda" va hokazo.
   Ro'yxat kichik bo'ladi.
3. **Yengil stemming (tajriba):** eng ko'p uchraydigan qo'shimchalar uzunlik cheklovi bilan
   so'z oxiridan kesiladi: kelishiklar (-ning, -ni, -ga/-ka/-qa, -da/-ta, -dan/-tan), ko'plik
   (-lar), egalik (-im, -ing, -i, -si, -imiz, -ingiz) va ba'zi so'z yasovchilar (-lik, -dagi,
   -gan). Stemming baholash to'plamida stemmingsiz variant bilan solishtiriladi. Agar natija
   yaxshilanmasa, u o'chiriladi.

So'rov `websearch_to_tsquery` emas, `plainto_tsquery` mantiqida tuziladi, lekin so'zlar `|` (OR)
bilan bog'lanadi. Natijalar `ts_rank_cd` bilan tartiblanadi. AND bilan bog'lansa, tabiiy tildagi
savollarga juda kam natija chiqadi.

## Gibrid qidiruv

```
search(query, alt_queries=[], doc_types=None, status='in_force', limit=8)
  har bir ifoda uchun: FTS top-50 + vektor top-50 (HNSW, ef_search=80)
  → RRF: score = Σ 1/(k + rank), k = 60
  → bitta modda bo'yicha bitta natija (eng yaxshi bo'lagi)
  → filtrlar (doc_type, status) SQL'ning o'zida
  → limit
```

- Natijada quyidagilar bo'ladi: hujjat nomi va raqami, modda raqami va nomi, yo'l, matndan
  parcha (≈400 belgi), havola `https://lex.uz/docs/{id}#{elem_id}`, holat, `last_change_date`.
- Raqamli so'rovlar ("161-modda", "PF-60") alohida aniqlanadi: hujjat yoki modda nomi
  to'g'ridan-to'g'ri topilsa, u birinchi o'ringa qo'yiladi. Asosiy ish 3-bosqichdagi
  `get_article` va `find_document` vositalarida.
- Qidiruv RAM'da bitta `Embedder` va bitta connection pool bilan ishlaydi.

## Baholash to'plami

- Fayl: `eval/questions.yaml`. Har bir yozuvda: `id`, `question` (oddiy odam tilida),
  `expected` (bir yoki bir nechta `{document: lex_id, article: "161"}`), `tags` (mavzu, uslub:
  rasmiy, so'zlashuv, imloviy xatoli).
- Dastlabki 80–100 ta savolni men yozaman: korpusdagi moddalar asosida, turli mavzularda.
  Savollar ataylab moddadagi so'zlar bilan emas, odam qanday so'rasa shunday yoziladi
  ("ishdan bo'shatishsa nima qilaman"). Ularni ko'rib chiqishingiz va real savollar qo'shishingiz
  kerak. Mening savollarim "matnni bilgan odam" yozgan savollar bo'lgani uchun natijani biroz
  yaxshi ko'rsatishi mumkin.
- Metrikalar: Recall@5, Recall@10 (kutilgan moddalardan kamida bittasi top-k'da bo'lsa) va MRR.
  Natija `eval/results/<sana>-<izoh>.json`ga yoziladi va git'ga qo'shiladi, shunda
  o'zgarishlar tarixi ko'rinadi.
- Baholash testlarda emas, alohida CLI bilan ishlaydi, chunki unga baza va model kerak.

## Modullar

```
src/qonunshunos/
  config.py          Settings (DSN, model yo'li, limitlar), env'dan o'qiladi
  db/                connect(), migrate(), migrations/*.sql
  text/chunk.py      Unit → bo'laklar
  text/fts.py        fold, stopwords, stem, to_fts_text
  index/embed.py     Embedder (onnxruntime), model yuklash
  index/writer.py    ParsedDocument + card → documents/sections/chunks
  search/hybrid.py   search(), RRF
eval/
  questions.yaml, results/
```

Yangi bog'liqliklar: `psycopg[binary,pool]`, `pgvector`, `onnxruntime`, `tokenizers`, `numpy`,
`pyyaml`.

## Testlar

- `chunk`, `fts` (fold, stem) va RRF birlashtirish uchun sof unit testlar.
- `writer` → baza → `search` uchun integratsion testlar (`-m db`). Ular fixture hujjatlardan
  mitti baza quradi. Embedding o'rniga deterministik soxta embedder ishlatiladi, shunda testga
  model kerak bo'lmaydi.
- `Embedder` uchun bitta test: model mavjud bo'lsa ishlaydi, aks holda o'tkazib yuboriladi.

## Xavflar

- **e5-small o'zbek tilida zaif bo'lishi mumkin.** Buni baholash to'plami ko'rsatadi. Zaxira
  variantlar: `multilingual-e5-base` (≈280 MB int8, sekinroq) yoki FTS'ga ko'proq og'irlik berish.
- **Uzun moddalarda kirish gapi takrorlanadi.** Bu indeks hajmini ≈10–15 foizga oshiradi va
  bunga yo'l qo'yiladi.
- **`myserver`dagi PostgreSQL boshqa ilovalar bilan umumiy.** HNSW indeksi taxminan 0,5 GB
  bo'ladi. `shared_buffers` 5-bosqichda ko'rib chiqiladi.
