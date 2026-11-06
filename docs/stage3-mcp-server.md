# 3-bosqich: MCP server va tool'lar

Holat (2026-11-06): 📝 dizayn, ko'rib chiqilmoqda. Tegishli hujjatlar: [PLAN.md](../PLAN.md)
(6-bo'lim), [2-bosqich](stage2-index-search.md).

## Maqsad

2-bosqichdagi qidiruv kutubxonasi ustiga MCP server qurish. AI yordamchi (Claude, ChatGPT,
Cursor) bu server orqali qonunlarni qidiradi, moddalarni o'qiydi va javobida lex.uz'ga aniq havola
beradi. Bu bosqichda kirish (OAuth) va limitlar yo'q, server faqat mahalliy kompyuterda sinaladi.
OAuth, limitlar va ommaviy manzil keyingi bosqichlarda qo'shiladi (4- va 5-bosqichlar).

## Tayyor bo'lish mezonlari

- `qonunshunos serve` Streamable HTTP serverini ishga tushiradi (`http://127.0.0.1:8000/mcp`).
  `qonunshunos serve --stdio` esa mahalliy mijozlar uchun.
- 6 ta tool ishlaydi: `search_law`, `get_article`, `get_document`, `get_section`,
  `find_document`, `list_codes`. Bundan tashqari `yuridik_savol` prompti va `lex://` resurslari
  bor.
- MCP Inspector'da barcha tool'lar ko'rinadi, ularning sxemasi to'g'ri va har biri haqiqiy
  bazada ishlaydi.
- **Claude Code bilan qo'lda sinov:** 10 ta savolda (baholash to'plamidan, turli mavzularda) AI
  `search_law`ni `alt_queries` bilan chaqiradi, kerakli moddani `get_article` bilan o'qiydi va
  javobda to'g'ri lex.uz havolasini beradi. Natija shu hujjatning "Natija" bo'limiga yoziladi.
- Har bir javob ixcham: qidiruv natijasi ≈1500 tokendan, bitta sahifa ≈2500 tokendan oshmaydi.
- Tool chaqiruvlari `usage_events` jadvaliga yoziladi (hozircha `user_id`siz). Statistika
  boshidan yig'ilishi kerak (PLAN, 1-bo'lim).
- Kechikish (server ichida): `search_law` ≤ 300 ms, qolganlari ≤ 50 ms.
- `uv run pytest` o'tadi. Formatlash va hujjatni topish testlari bazasiz ishlaydi, tool testlari
  esa `-m db` bilan.

## Ishlar tartibi

1. Ma'lumotni tozalash: `0004` migratsiyasi (`doc_kind`, `display_title`, `usage_events`),
   `writer` va qayta indekslash (embedding qayta hisoblanmaydi).
2. `mcp/resolve.py`: hujjat va modda havolalarini aniqlash + testlar.
3. `mcp/format.py`: javob matnlari, sahifalash + snapshot testlar.
4. `mcp/tools.py` + `mcp/server.py`: `MCPServer`, lifespan (pool, embedder), tool'lar, prompt,
   resurslar, `serve` CLI.
5. `-m db` testlari: tool'larni SDK'ning xotiradagi mijozi orqali chaqirish.
6. MCP Inspector va Claude Code bilan sinov, tool tavsiflarini sozlash, "Natija" bo'limi.

## Texnologiyalar

- **MCP Python SDK 2.x** (`mcp>=2.3`). 2.x'da `FastMCP` `MCPServer` deb qayta nomlangan
  (`from mcp.server.mcpserver import MCPServer`). Yangi loyiha bo'lgani uchun to'g'ridan-to'g'ri
  2.x'dan boshlaymiz, 1.x'dan ko'chirish kerak bo'lmaydi.
- Transport: Streamable HTTP, `stateless_http=True`, `json_response=True`. Sessiya holati
  saqlanmaydi, shuning uchun server qayta ishga tushsa mijoz uzilmaydi. Bu nginx ortida ham
  oddiyroq ishlaydi. ASGI server sifatida SDK bilan birga keladigan `uvicorn` ishlatiladi:
  bitta jarayon, chunki model RAM'da bitta bo'lishi kerak.
- Tool'lar sinxron funksiya bo'lib qoladi. SDK ularni alohida oqimda (`anyio.to_thread`)
  ishlatadi. Baza — `psycopg_pool.ConnectionPool` (min 1, max 4), embedder — bitta nusxa. Ikkalasi
  ham lifespan'da yaratiladi.
- Yangi bog'liqlik faqat `mcp`. `starlette` va `uvicorn` u bilan birga keladi.

## Ma'lumotni tozalash (migratsiya 0004)

Bazada hozir ikkita muammo bor. Tool'lar ularga tayanadi, shuning uchun avval shular tuzatiladi.

1. **Hujjat turi har xil yozilgan.** `doc_type` card1'dan qanday kelgan bo'lsa, shunday
   saqlangan: `Закон`, `Қонун`, `Qonun`, `Кодекс`. Kartochka ba'zan ruscha keladi. Yangi
   `doc_kind` ustuni qo'shiladi, unda qiymatlar bitta ro'yxatdan olinadi: `konstitutsiya`,
   `kodeks`, `qonun`, `farmon`, `qaror` (Prezident), `vm_qarori`, `buyruq` (vazirlik),
   `boshqa`. Mos kelish jadvali `index/doctype.py`da saqlanadi va lotin, kirill hamda rus
   shakllarini qamraydi. `search_law(doc_types=...)` va `find_document(doc_type=...)` shu
   qiymatlarni qabul qiladi.
2. **Qisqa nom notekis.** Hozirgi `short_title`ning ko'rinishi har xil: "Qonun OʻRQ-641:
   Nogironligi …", "OʻRQ-642: Aholi bandligi toʻgʻrisida", "Qonun OʻRQ-610: fuqaroligi
   toʻgʻrisida" (bunda sarlavha boshidan kerakli so'z tushib qolgan). Yangi `display_title`
   odam o'qiydigan shaklda bo'ladi: "Aholi bandligi toʻgʻrisidagi Qonun (OʻRQ-642)",
   "Mehnat kodeksi", "Konstitutsiya". Chunk sarlavhalari ham shu nomdan quriladi. Sarlavhalar
   o'zgargani uchun ular uchun FTS va embedding qayta hisoblanadi. Bu 16 ming bo'lak uchun
   mahalliy kompyuterda bir necha daqiqa oladi. Keyin baholash qayta ishga tushiriladi va R@10
   tushib ketmaganiga ishonch hosil qilinadi.

Shu migratsiyada `usage_events` jadvali ham yaratiladi (PLAN, 5-bo'lim): `user_id` (hozircha
NULL), `tool`, `ts`, `latency_ms`, `result_count`, `ok`, `args` (jsonb, qisqartirilgan:
qidiruv so'zi ≤ 300 belgi). Foydalanuvchi va limitlar 4-bosqichda qo'shiladi.

## Hujjat va moddani aniqlash (`mcp/resolve.py`)

AI hujjatni har xil ko'rinishda nomlaydi. Shuning uchun `get_article`, `get_document` va
`get_section` hujjatni ID bilan ham, nom bilan ham qabul qiladi:

| Kirish | Qanday topiladi |
|---|---|
| `-6257288`, `6257288`, `https://lex.uz/docs/-6257288#-6257549` | ID (musbat bo'lsa manfiyga aylantiriladi). URL'dagi `#elem` ham hisobga olinadi |
| `OʻRQ-642`, `PF-60`, `orq 642` | `number` bo'yicha, `fold` bilan normalizatsiya qilib aniq solishtiriladi |
| `Mehnat kodeksi`, `MK`, `mehnat` | qisqartmalar jadvali (`MK`, `JK`, `FK`, `SK`, `MJtK` …) va `title_norm` bo'yicha trigram |

- Agar bitta hujjat aniq topilsa (trigram o'xshashligi ≥ 0,5 va keyingisidan sezilarli yuqori
  bo'lsa), o'sha hujjat olinadi. Aks holda tool xato qaytarmaydi: 3–5 ta nomzodni ID'lari bilan
  ko'rsatadi, shunda AI to'g'ri ID bilan qayta chaqiradi.
- **Modda raqami:** `161`, `161-modda`, `10¹`, `10-1`, `10^1` — hammasi bir xil
  normalizatsiya qilinadi (daraja belgilari, defis). Kodeks va qonunlarda avval `modda` qidiriladi,
  topilmasa `band` qidiriladi. Farmon va qarorlarda esa aksincha. Bir xil raqamli band bir nechta
  ilovada bo'lishi mumkin, masalan Nizomning 5-bandi va Ro'yxatning 5-bandi. Bunday holatda yo'li
  bilan birga variantlar ro'yxati qaytariladi.

## Tool'lar

Umumiy qoidalar:

- **Javob formati — ixcham Markdown matni**, JSON emas. Natijani AI o'qiydi. Matn JSON'dan
  ≈30–40 % kam token oladi va AI uni to'g'ridan-to'g'ri iqtibos qila oladi. Har bir javob
  oxirida manba qatori turadi: `Manba: lex.uz, <havola>`.
- Har bir moddada aniq havola (`https://lex.uz/docs/-{id}#{elem_id}`), hujjat holati va
  oxirgi o'zgartirish ma'lumoti bo'ladi. Oxirgi o'zgartirish `changes`dagi so'nggi yozuvdan
  olinadi, masalan: "OʻRQ-963, 20.09.2024 tahririda".
- Uzun matn sahifalarga bo'linadi: bitta sahifa ≈9000 belgi (≈2000 token). Bo'linish xatboshi
  chegarasida bo'ladi. Javob oxirida "1/3-sahifa, keyingisi: `page=2`" deb yoziladi.
  95 % moddalar 3100 belgidan qisqa, ya'ni ko'pchiligi bitta sahifaga sig'adi.
- Kuchini yo'qotgan hujjat so'ralsa, matn berilmaydi. O'rniga uning rekvizitlari va
  "kuchini yo'qotgan: sana, sababi" qaytariladi (`lost_force_at`, `lost_force_reason`).
- Noto'g'ri kirishda tool xato bilan tugamaydi. U AI'ga nima qilish kerakligini aytadigan matn
  qaytaradi, masalan "Mehnat kodeksida 999-modda yo'q. `get_document` bilan mundarijani
  ko'ring". Xato (`is_error`) faqat kutilmagan nosozlikda qaytariladi.
- Barcha tool'lar `readOnlyHint=true`, `openWorldHint=false` deb belgilanadi. Shunda mijozlar
  ularni har safar ruxsat so'ramasdan chaqira oladi.
- Kirish cheklovlari: `query` ≤ 300 belgi, `alt_queries` ≤ 2 ta, `limit` 1–15.

### `search_law(query, alt_queries=[], doc_types=None, limit=8)`

Gibrid qidiruv (`search.hybrid.search`). Bitta modda bo'yicha bitta natija qaytadi.

```
1. Mehnat kodeksi, 161-modda. Mehnat shartnomasini ish beruvchining tashabbusiga ko'ra bekor qilish
   <bo'lim > bob> · amalda · <oxirgi o'zgartirish>
   https://lex.uz/docs/-6257288#<elem_id>
   > Ish beruvchi mehnat shartnomasini quyidagi hollarda bekor qilishi mumkin: … (≈400 belgi)
2. …
To'liq matn: get_article(document=-6257288, article="161")
```

Tool tavsifi AI uchun yo'riqnoma vazifasini bajaradi. 2-bosqich shuni ko'rsatdi: AI savolni
rasmiy huquqiy tilga o'girsa, R@10 0,70 dan 0,88–0,91 gacha oshadi. Shuning uchun tavsifda aniq
yoziladi:

- `query`ga foydalanuvchi savolini o'zbek tilida (lotin) yoz. U boshqa tilda yoki kirillda
  so'rasa, avval o'zbek lotinchaga o'gir.
- `alt_queries`ga 1–2 ta qayta ifoda yoz: qonun matnida qanday yozilgan bo'lsa, o'shanday
  ("ishdan haydash" → "mehnat shartnomasini ish beruvchining tashabbusiga ko'ra bekor qilish").
- Natija parchasi to'liq emas. Javob berishdan oldin moddani `get_article` bilan o'qi.

### `get_article(document, article, page=1)`

Moddaning (yoki bandning) to'liq matni. Javobda sarlavha, yo'l, holat, havola, matn va
o'zgartirishlar ro'yxati bo'ladi. O'zgartirishlar ro'yxati ko'pi bilan 3 ta, eng oxirgilari
ko'rsatiladi. "LexUZ sharhi" (`comments`) normativ matn emas, shuning uchun bitta qatorda,
havola sifatida ko'rsatiladi.

### `get_document(document)`

Rekvizitlar va mundarija. Rekvizitlar: to'liq nom, turi, raqami, qabul qilingan sana, kuchga
kirgan sana, holati, qabul qilgan organ, tahrir sanasi va havola. Mundarija sarlavhalardan
iborat: qism, bo'lim, bob, paragraf, ilova. Har bir sarlavha yonida moddalar oralig'i ko'rsatiladi
("12-bob. <nomi> — 152–175-moddalar" ko'rinishida). Moddalar ro'yxati alohida
berilmaydi, chunki Mehnat kodeksida ular 593 ta. Mundarija ham uzun bo'lsa sahifalanadi.

### `get_section(document, section, page=1)`

Bob yoki bo'limning to'liq matni, ichidagi barcha moddalar bilan, sahifalab. `section` uchta
ko'rinishda berilishi mumkin: mundarijadagi qisqa yorliq (`12-bob`, `II bo'lim`, `2-ilova`),
mundarijadagi tartib raqami (`#14`) yoki sarlavha nomidan parcha. Bitta sahifada ham ≈9000 belgi
bo'ladi.

### `find_document(query, doc_type=None, year=None, include_lost_force=false, limit=10)`

Hujjatni nomi yoki raqami bo'yicha topadi: avval aniq raqam, keyin trigram. Har bir natijada ID,
nom, raqam, sana, holat va havola bo'ladi. Bu yagona tool, unda kuchini yo'qotgan hujjatlar ham
chiqishi mumkin, lekin faqat `include_lost_force=true` bo'lsa. Ular baribir rekvizitlari bilan
bazada saqlanadi.

### `list_codes()`

Amaldagi kodekslar ro'yxati: nomi, ID, tahrir sanasi va qisqartmasi. Bu ma'lumot kam
o'zgaradi, shuning uchun server xotirasida 1 soat saqlanadi.

## Server yo'riqnomasi, prompt va resurslar

- **`instructions`** (MCP `initialize` javobida mijozga beriladi), qisqa ish tartibi:
  1. `search_law`, 2. `get_article`, 3. aniq moddalarga havola bilan javob. Bundan tashqari:
  faqat amaldagi tahrir indekslangan; eng yangi hujjatlar matni bazada hali bo'lmasligi mumkin;
  javob yuridik maslahat emas. Matn ingliz tilida yoziladi, misollar o'zbekcha bo'ladi.
- **Prompt `yuridik_savol(savol)`**: shu tartibni to'liqroq yozadi va oxirida "bu yuridik
  maslahat emas" ogohlantirishini talab qiladi. claude.ai'da u slash-buyruq sifatida
  ko'rinadi.
- **Resurslar:** `lex://document/{id}` (rekvizitlar va mundarija) va
  `lex://document/{id}/article/{n}`. Ular xuddi shu formatlovchilardan foydalanadi. Ko'p
  mijozlar resurslarni avtomatik o'qimaydi, shuning uchun asosiy yo'l baribir tool'lar.

## Modullar

```
src/qonunshunos/
  index/doctype.py   card1 shakli → doc_kind, display_title
  mcp/__init__.py
  mcp/resolve.py     hujjat (ID / raqam / nom) va modda raqamini aniqlash
  mcp/format.py      Markdown formatlovchilar, sahifalash
  mcp/tools.py       tool funksiyalari (baza + formatlash, MCP'siz ham chaqiriladi)
  mcp/server.py      MCPServer, lifespan, tool/prompt/resurs ro'yxati, /healthz, usage_events
  db/migrations/0004_doc_kind_usage.sql
```

`tools.py` MCP'ga bog'liq emas: uning funksiyalari connection va embedder oladi va matn
qaytaradi. Shunda ularni testda va CLI'da (`qonunshunos tool get_article …` — qo'lda tekshirish
uchun) to'g'ridan-to'g'ri chaqirish mumkin.

## Testlar

- `resolve`: ID, URL, raqam va qisqartmalarni aniqlash; modda raqamini normalizatsiya qilish
  (`10¹`, `10-1`, `161-modda`).
- `format`: sahifalash (xatboshi chegarasi, sahifalar soni) va asosiy javoblar uchun snapshot
  testlar (fixture'lardan qurilgan ma'lumot bilan).
- `-m db`: mitti bazada (2-bosqichdagi fixture'lar va soxta embedder) har bir tool chaqiriladi:
  topildi, topilmadi, bir nechta nomzod, kuchini yo'qotgan va sahifalangan holatlar.
- MCP protokoli darajasida SDK'ning xotiradagi mijozi orqali bitta test: `tools/list` 6 ta
  tool'ni annotatsiyalari bilan qaytaradi, `tools/call` `search_law` uchun matn qaytaradi.
- Claude Code bilan sinov qo'lda bajariladi va natijasi shu hujjatga yoziladi. U `pytest`ga
  kirmaydi.

## Xavflar

- **AI `alt_queries`ni ishlatmasligi mumkin.** Unda sifat 0,70 ga tushadi. Shuning uchun
  sinovda buni alohida tekshiramiz va kerak bo'lsa tavsifni kuchaytiramiz. Natija oxirida eslatma
  ham beriladi ("`alt_queries` berilmadi: rasmiy ifoda bilan qayta qidirish natijani
  yaxshilaydi").
- **SDK 2.x yangi.** API hali o'zgarishi mumkin, shuning uchun versiya `uv.lock`da qotiriladi.
  Agar claude.ai yoki ChatGPT konnektori bilan muammo chiqsa (4–5-bosqich), shu bosqichda
  aniqlanadi.
- **Hujjat nomini noto'g'ri aniqlash.** Masalan, "Fuqarolik kodeksi"ning ikki qismi va
  "Fuqarolik protsessual kodeksi" bir-biriga o'xshaydi. Shuning uchun ishonch past bo'lsa tool
  tanlamaydi, nomzodlar ro'yxatini qaytaradi. Qisqartmalar jadvali qo'lda to'ldiriladi.
- **Qayta indekslash (sarlavhalar o'zgaradi) baholash natijasini biroz o'zgartirishi mumkin.**
  Shuning uchun undan keyin `eval` qayta ishga tushiriladi va natija
  [stage2-experiments.md](stage2-experiments.md)ga yoziladi.
