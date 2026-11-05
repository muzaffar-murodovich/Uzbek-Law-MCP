# O'zbek tilidagi yuridik qidiruv: tajribalar jurnali

Qonunshunos loyihasining 2-bosqichi (2026-11-05). Bu hujjatda o'zbek tilidagi qonun matnlari
bo'yicha qidiruv qanday qurilgani, qanday o'lchangani va har bir qaror qaysi raqamga
asoslangani yozilgan. Dizayn: [stage2-index-search.md](stage2-index-search.md).

## Qisqacha

- **Vazifa.** Oddiy odamning savoliga ("Ish beruvchi meni sababsiz ishdan bo'shatishi
  mumkinmi?") lex.uz'dagi aniq moddani topish. Natija AI yordamchiga (Claude, ChatGPT) MCP
  orqali beriladi.
- **Yechim.** Gibrid qidiruv. To'liq matnli qidiruv (PostgreSQL FTS va o'zbek tili uchun
  yozilgan normalizatsiya) hamda semantik qidiruv (embedding va pgvector) natijalari
  Reciprocal Rank Fusion (RRF) bilan birlashtiriladi.
- **O'lchov.** Uchta mustaqil savollar to'plami tuzildi: qo'lda yozilgan, LLM yaratgan va LLM
  hakam tekshirgan. Asosiy metrika — Recall@10.
- **Natija.** Real ishlash sharoitida (AI savolni rasmiy tilga o'girib qidiradi) to'g'ri modda
  top-10 ichida **91%** (qo'lda yozilgan savollar) va **88%** (LLM yaratgan savollar) hollarda
  topiladi. Boshlang'ich holatda bu ko'rsatkich 66% edi.
- **Eng katta yutuqlar:**
  - FTS'da IDF og'irligi (+11 punkt);
  - HNSW indeksidagi yashirin muammo topilib tuzatildi;
  - embedding modellari o'z ma'lumotimizda solishtirildi.

## 1. Ma'lumotlar

| | |
|---|---|
| Manba | lex.uz, o'zbek tili (lotin), faqat amaldagi tahrir |
| Korpus | Konstitutsiya, 20 ta amaldagi kodeks, 65 ta qonun: jami 86 ta hujjat |
| Birliklar | modda va band, jami ≈11 ming |
| Bo'laklar (chunk) | 16 657 ta, o'rtacha ≈1000 belgi |

Qonunlar 1590 ta lotin qonun ichidan tanlandi: amaldagi, o'zgartish kiritmaydigan "asosiy"
qonunlardan 308 tasi ajratildi, ulardan fuqarolar ko'p so'raydigan mavzulardagi 65 tasi olindi
(pensiya, iste'molchilar huquqlari, kredit, harbiy xizmat, OSAGO va h.k.). Ro'yxat:
[eval/corpus/laws.txt](../eval/corpus/laws.txt).

**Bo'laklash.** Modda yoki band 1500 belgidan oshmasa, bitta bo'lak bo'ladi. Uzunroq bo'lsa,
xatboshi chegarasida ≈1100 belgilik bo'laklarga bo'linadi. Moddaning kirish gapi ("Quyidagi
sabablar ...:") har bir bo'lakka takrorlanadi, aks holda sanab o'tilgan bandlar ma'nosiz qoladi.
Har bir bo'lakka kontekst sarlavhasi qo'shiladi: hujjat, bob, modda raqami va nomi.

## 2. Qidiruv

```
savol ─┬─ FTS: normalizatsiya → stemming → IDF og'irlikli OR qidiruv ── top-50 ─┐
       └─ vektor: e5 embedding → HNSW (pgvector, halfvec) ────────────── top-50 ─┴─ RRF → modda bo'yicha
                                                                                  eng yaxshi bo'lak → top-k
```

- **Normalizatsiya.** Apostroflar birxillashtiriladi (`o' o‘ o’ oʻ` → `o`), matn kichik harfga
  o'tkaziladi, to'xtatuvchi so'zlar olib tashlanadi.
- **Stemming.** O'zbek tili uchun tayyor stemmer yo'q, shuning uchun o'zimiz yozdik. Har bir
  morfologik "slot"dan bittadan qo'shimcha o'ngdan chapga kesiladi: kelishik → egalik → ko'plik.
  Masalan: `xodimlarning` → `xodim`, `moddasining` → `modda`, `qoidalariga` → `qoida`.
- **AI qayta yozishi.** MCP'da `search_law(query, alt_queries)` vositasini AI yordamchi
  chaqiradi. U foydalanuvchi savolini rasmiy yuridik tilga o'giradi. Barcha ifodalar bitta RRF'da
  birlashtiriladi.

## 3. Baholash metodologiyasi

### Savollar to'plamlari

| To'plam | Hajm | Qanday tuzilgan | Kuchli tomoni | Kamchiligi |
|---|---|---|---|---|
| Qo'lda yozilgan ([questions.yaml](../eval/questions.yaml)) | 97 | Mavzular tanlanib, moddalar asosida oddiy odam tilida yozildi, kutilgan moddalar skript bilan tekshirildi | Aniq, mashhur mavzular | Muallif moddalarni ko'rib turib yozgan, shuning uchun optimistik |
| LLM yaratgan ([questions_llm.yaml](../eval/questions_llm.yaml)) | 100 | Tasodifiy moddalar GPT-5.4'ga berilib, "yurist bo'lmagan odam qanday so'raydi" deb so'raldi | Xilma-xil, real hayotiy vaziyatlar | Bitta savolga bir nechta modda javob bo'lishi mumkin |
| LLM hakam | 100 ning ustiga | Qidiruv topgan top-5 moddani GPT-5.4 tekshirdi va savolga bevosita javob berganlari kutilgan javoblarga qo'shildi (pooled relevance judgments) | Haqiqatan to'g'ri topilgan javoblar "xato" deb hisoblanmaydi | Faqat bizning tizim topganlari tekshirildi, ya'ni o'lchov tizimga biroz moyil |

### AI qayta yozishini simulyatsiya qilish

Real foydalanishda savolni AI rasmiy tilga o'giradi. Buni o'lchash uchun ikki xil `alt` sinaldi:

- **qo'lda:** muallif yozgan, moddalarni bilgan holda, ya'ni optimistik;
- **LLM:** GPT-5.4 faqat savolni ko'radi, moddani ko'rmaydi
  ([alt_llm.json](../eval/alt_llm.json)). Bu haqqoniy o'lchov.

### Metrikalar

- **Recall@k:** kutilgan moddalardan kamida bittasi birinchi k ta natija ichida bo'lgan
  savollar ulushi.
- **MRR:** birinchi to'g'ri natija o'rnining teskari qiymati, 10 tagacha hisoblanadi.

Natijalar [eval/results/](../eval/results/) papkasida saqlanadi va git'da turadi, shuning uchun
o'zgarishlar tarixi ko'rinadi.

## 4. Tajribalar

### 4.1. Boshlang'ich holat va FTS

Korpus: 21 ta hujjat. To'plam: qo'lda yozilgan 77 ta savol, `alt`siz.

| Tajriba | FTS R@10 | Vektor R@10 | Gibrid R@10 | Gibrid MRR |
|---|---|---|---|---|
| Boshlang'ich: `ts_rank_cd`, OR qidiruv | 0,45 | 0,61 | 0,66 | 0,36 |
| Stemmingsiz | 0,43 | — | 0,66 | 0,40 |
| **IDF og'irligi + sarlavha bonusi** | **0,71** | — | **0,77** | 0,43 |
| IDF, stemmingsiz | 0,71 | — | 0,74 | 0,47 |

- **Muammo.** OR qidiruvda "ish", "kun", "necha" kabi juda ko'p uchraydigan so'zlar natijani
  egallab olardi.
- **Yechim.** Har bir so'z BM25 uslubidagi IDF bilan tortiladi. Hujjat chastotalari `ts_stat`
  orqali olinib, `fts_stats` jadvalida saqlanadi. Moddaning sarlavhasida moslik bo'lsa,
  qo'shimcha og'irlik beriladi. Bo'laklarning 5 foizidan ko'pida uchraydigan so'zlar faqat ballga
  hissa qo'shadi, nomzodlarni tanlashda ishtirok etmaydi.
- **Stemming.** Uning ta'siri shovqin darajasida chiqdi (±0,03), shuning uchun qoldirildi.

### 4.2. RRF parametrlari

`k` (10, 30, 60), ro'yxatlar og'irligi va nomzodlar soni (30, 50, 100) bo'yicha oflayn sinov
o'tkazildi. Barcha variantlar 0,71–0,77 oralig'ida chiqdi, ya'ni 77 ta savolda bu shovqin. Shu
sababli standart `k=60` va top-50 qoldirildi. **Saboq:** kichik baholash to'plamida mayda
parametrlarni sozlashning ma'nosi yo'q.

### 4.3. Yashirin muammo: HNSW indeksining aniqligi

- **Kuzatuv.** fp32 model int8'dan **yomonroq** natija berdi: vektor R@10 0,39, int8'da esa 0,61.
  Lekin ikkala modelning vektorlari 0,985–0,99 kosinus o'xshashlikka ega edi.
- **Tahlil.** HNSW natijasi aniq qidiruv (indekssiz) bilan solishtirildi. Top-50 ning atigi
  **≈70%** i mos keldi.
- **Sabab.** e5 modelida o'xshashlik qiymatlari juda tor oraliqqa to'planadi: top-50 orasidagi
  farq kosinus masofasida bor-yo'g'i 0,01–0,03. Standart graf parametrlari (`m=16`,
  `ef_construction=64`) bunday zich joyda ko'p qo'shnilarni yo'qotadi. int8 va fp32 orasidagi
  "farq" aslida graf qanday qurilganining tasodifi edi.
- **Yechim.** `m=32`, `ef_construction=200`, `ef_search=100` qo'yildi, natijada aniq top-50 ning
  ≈90% i topiladigan bo'ldi. `relaxed_order` olib tashlandi. Hujjat turi bo'yicha filtr
  bo'lmaganda `documents` jadvali bilan JOIN qilinmaydi.
- **Saboq.** Modellarni solishtirishda vektor qidiruvni aniq (brute-force) usulda o'tkazish
  kerak, aks holda indeks shovqini model farqidek ko'rinadi.

### 4.4. Korpus kengaytirildi, AI qayta yozishi qo'shildi

Korpus: 86 ta hujjat. To'plam: qo'lda yozilgan 97 ta savol.

| Holat | FTS R@10 | Vektor R@10 | Gibrid R@10 | Gibrid MRR |
|---|---|---|---|---|
| Faqat xom savol | 0,67 | 0,51 | 0,70 | 0,36 |
| + qo'lda yozilgan `alt` | 0,95 | 0,69 | 0,95 | 0,61 |
| **+ LLM yozgan `alt`** (haqqoniy) | 0,89 | 0,64 | **0,91** | 0,56 |

### 4.5. LLM yaratgan savollar

To'plam: LLM yaratgan 100 ta savol. Korpus: 86 ta hujjat.

| Holat | Gibrid R@10 | Gibrid MRR |
|---|---|---|
| Faqat manba modda, xom savol | 0,31 | 0,16 |
| + LLM hakam qo'shgan moddalar, xom savol | 0,70 | 0,38 |
| **+ hakam + LLM yozgan `alt`** | **0,88** | 0,63 |

Hakamdan oldin 0,31 chiqqani savollarning ko'pchiligiga bir nechta modda javob bo'lishini
ko'rsatadi. Bu qonunchilikda odatiy hol: masalan, bir masala ham Fuqarolik kodeksida, ham
alohida qonunda tartibga solingan bo'ladi. Hakamdan keyingi natija qo'lda yozilgan to'plamga
juda yaqin chiqdi (0,70/0,88 va 0,70/0,91). Demak, natija bitta muallifning savollariga bog'liq
emas.

### 4.6. Embedding modellarini solishtirish

Bu sinovda vektor qidiruv aniq usulda (numpy) o'tkazildi, FTS esa ishlab chiqarishdagidek
qoldi. Har bir model barcha 16 657 ta bo'lakni o'zi embedding qildi. Skript:
[scripts/bench_embeddings.py](../scripts/bench_embeddings.py).

To'plam: qo'lda yozilgan 97 ta savol, qo'lda yozilgan `alt`.

| Model | Parametr | O'lcham | Vektor R@10 | Gibrid R@10 | Vektor, `alt` bilan | Gibrid, `alt` bilan | Gibrid MRR, `alt` bilan | Embedding vaqti (Mac, GPU) |
|---|---|---|---|---|---|---|---|---|
| multilingual-e5-small | 118M | 384 | 0,57 | 0,70 | 0,77 | 0,97 | 0,72 | 2,4 daq. |
| uzbek-e5-small | 118M | 384 | 0,60 | 0,71 | 0,88 | 0,98 | 0,75 | 1,4 daq. |
| multilingual-e5-base | 278M | 768 | 0,73 | 0,75 | 0,90 | 0,98 | 0,69 | 10 daq. |
| granite-97m-multilingual-r2 | 97M | 384 | 0,40 | 0,64 | 0,60 | 0,98 | 0,71 | 5 daq. |
| granite-311m-multilingual-r2 | 311M | 768 | 0,52 | 0,67 | 0,81 | 0,99 | 0,74 | 19 daq. |
| **harrier-oss-v1-270m** | 268M | 640 | **0,80** | **0,83** | **0,94** | **0,99** | **0,79** | 20 daq. |
| embeddinggemma-300m | 300M | 768 | — | — | — | — | — | gated, yuklab bo'lmadi |
| bge-m3 | 568M | 1024 | *hisoblanmoqda* | | | | | |

LLM `alt` va LLM savollari bilan natijalar: *hisoblanmoqda*, 4.7-bo'limga qo'shiladi.

Ishlab chiqarish narxi. Server 2 vCPU, GPU yo'q, shuning uchun o'lchov Mac protsessorida 2 ta
oqim bilan qilindi:

| Model | Bitta savol | Bitta bo'lak | Xotira |
|---|---|---|---|
| e5-small | 6 ms | 21 ms | ≈0,5 GB |
| harrier-270m (fp32) | 30 ms | 136 ms | ≈1,1 GB |

Kuzatuvlar:

- **AI qayta yozganda modellar orasidagi farq deyarli yo'qoladi:** gibrid natija hamma modelda
  0,97–0,99. Model sifati asosan xom, so'zlashuv tilidagi savollarda ko'rinadi.
- **harrier-270m eng kuchli**, ayniqsa xom savollarda (vektor R@10 0,80, e5-small'da 0,57).
  Lekin bo'lak embedding qilish 6,5 barobar qimmat va vektori kattaroq.
- **uzbek-e5-small** o'zbek tiliga moslashtirilgan e5-small. U hozirgi model bilan bir xil
  narxda, lekin `alt` bilan vektor qidiruvda aniq yaxshiroq (0,88, e5-small'da 0,77).
- **granite-97m o'zbek tilida zaif chiqdi**, garchi o'zbek tili uning o'qitilgan tillari
  ro'yxatida bo'lsa ham.

### 4.7. Yakuniy solishtirish (LLM `alt`, ikkala to'plam)

*Hisoblanmoqda.*

## 5. LLM'dan foydalanish

| Ish | Model | Token |
|---|---|---|
| 97 ta savolni rasmiy tilga o'girish | gpt-5.4 | ≈21 ming |
| 100 ta savol yaratish (≈140 ta modda sinaldi, oddiy odam so'ramaydiganlari tashlab ketildi) | gpt-5.4 | ≈95 ming |
| Hakamlik (100 savol × top-5 modda) | gpt-5.4 | ≈201 ming |
| 100 ta LLM savolini rasmiy tilga o'girish | gpt-5.4 | ≈20 ming |

**Hodisa.** OpenAI'ning bepul kunlik limiti tugaganda API xato qaytarmaydi, shunchaki pullik
hisobdan yecha boshlaydi. Birinchi versiyadagi "429 kelsa keyingi kalitga o't" mantiqi buni
sezmadi va ≈80 ming token pullik bo'lib ketdi.

**Tuzatish.** Mahalliy hisob qo'shildi ([llm.py](../src/qonunshunos/llm.py),
`data/llm_usage.json`): har bir kalit va har bir model toifasi uchun UTC kuni bo'yicha sarf
yuritiladi va so'rov bepul limitdan **oldin** to'xtatiladi. Ro'yxatda yo'q model chaqirilmaydi.
Testlar bilan himoyalangan.

## 6. Boshqa muhandislik qarorlari

- **Docker'dan voz kechildi.** Mahalliy muhitda Homebrew PostgreSQL 17 + pgvector ishlatiladi.
  `home` server baza ushlamaydi: u embedding hisoblaydi va SSH tunnel orqali to'g'ridan-to'g'ri
  `myserver`dagi PostgreSQL 16'ga yozadi.
- **pgvector versiyasi.** Ubuntu 24.04 repozitoriyasida 0.6 bor, bizga esa ≥ 0.8 kerak
  (`halfvec`, `iterative_scan`). Server uchun PGDG repozitoriyasi ishlatiladi.
- **Parser.** Qonunlar qo'shilganda uchta yangi holat chiqdi va tuzatildi:
  - parlament muhri (`GRIF_PARLAMENT`);
  - o'zgartish matni ichida qo'shtirnoqqa olingan modda ("“67²-modda...”") alohida modda deb
    olinmasligi kerak;
  - tahririyat izohlari (`EXPLANATION`).

  Hozir 86 ta hujjat ogohlantirishsiz parse bo'ladi.

## 7. Ochiq masalalar

- **Model tanlovi.** 4.7-bo'lim natijasiga qarab qaror qilinadi: harrier sifati yoki
  uzbek-e5-small arzonligi.
- **Haqiqiy foydalanuvchi savollari** hali yo'q. Xizmat ishga tushgach, so'rovlar anonim holda
  yig'ilib, baholash to'plamiga qo'shiladi.
- **Farmon va qarorlar** baholash to'plamida hali yo'q.
- **Yuridik domenga moslashtirish.** LLM yordamida yaratilgan "savol → modda" juftliklarida
  embedding modelini qo'shimcha o'qitish (fine-tuning).

## Qayta ishlab chiqarish

```bash
uv run qonunshunos crawl-sample && uv run qonunshunos crawl --ids-file eval/corpus/laws.txt
uv run qonunshunos db-migrate && uv run qonunshunos index
uv run qonunshunos eval --alt-file eval/alt_llm.json
uv run qonunshunos eval --questions eval/questions_llm.yaml --alt-file eval/alt_llm_questions_llm.json
uv run --group bench python scripts/bench_embeddings.py --alt-file eval/alt_llm.json
```
