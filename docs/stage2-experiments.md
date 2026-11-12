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
| bge-m3 | 568M | 1024 | **0,90** | **0,85** | 0,94 | 0,98 | **0,80** | 27 daq. |


Ishlab chiqarish narxi. Server 2 vCPU, GPU yo'q, shuning uchun o'lchov Mac protsessorida 2 ta
oqim bilan qilindi:

| Model | Bitta savol | Bitta bo'lak | Xotira |
|---|---|---|---|
| e5-small | 6 ms | 21 ms | ≈0,5 GB |
| harrier-270m (fp32) | 30 ms | 136 ms | ≈1,1 GB |
| bge-m3 (fp32) | 55 ms | 186 ms | ≈2,3 GB (int8 ONNX'da ≈0,6 GB) |

Kuzatuvlar:

- **AI qayta yozganda modellar orasidagi farq deyarli yo'qoladi:** gibrid natija hamma modelda
  0,97–0,99. Model sifati asosan xom, so'zlashuv tilidagi savollarda ko'rinadi.
- **harrier-270m eng kuchli**, ayniqsa xom savollarda (vektor R@10 0,80, e5-small'da 0,57).
  Lekin bo'lak embedding qilish 6,5 barobar qimmat va vektori kattaroq.
- **uzbek-e5-small** o'zbek tiliga moslashtirilgan e5-small. U hozirgi model bilan bir xil
  narxda, lekin `alt` bilan vektor qidiruvda aniq yaxshiroq (0,88, e5-small'da 0,77).
- **granite-97m o'zbek tilida zaif chiqdi**, garchi o'zbek tili uning o'qitilgan tillari
  ro'yxatida bo'lsa ham.
- **bge-m3 xom savollarda eng kuchli** (vektor R@10 0,90).

### 4.7. Yakuniy solishtirish (LLM `alt`, ikkala to'plam)

Real sharoitga eng yaqin o'lchov: `alt` ifodalarni moddani ko'rmagan LLM yozgan. Vektor qidiruv
aniq usulda o'tkazilgan.

| Model | Qo'lda yozilgan savollar (97): vektor / gibrid R@10, xom | Qo'lda yozilgan savollar: gibrid R@10 / MRR, `alt` bilan | LLM savollari (100): vektor / gibrid R@10, xom | LLM savollari: gibrid R@10 / MRR, `alt` bilan |
|---|---|---|---|---|
| e5-small | 0,57 / 0,70 | 0,92 / 0,65 | 0,49 / 0,65 | 0,90 / 0,68 |
| uzbek-e5-small | 0,60 / 0,71 | 0,97 / 0,68 | 0,28 / 0,58 | 0,89 / 0,61 |
| e5-base | 0,73 / 0,75 | 0,95 / 0,68 | 0,49 / 0,64 | 0,91 / 0,73 |
| granite-97m | 0,40 / 0,64 | 0,92 / 0,66 | 0,15 / 0,50 | 0,88 / 0,61 |
| granite-311m | 0,52 / 0,67 | 0,93 / 0,70 | 0,20 / 0,55 | 0,88 / 0,67 |
| harrier-270m | 0,80 / 0,83 | 0,92 / 0,70 | 0,58 / 0,66 | **0,96** / 0,72 |
| **bge-m3** | **0,90 / 0,85** | **0,98 / 0,80** | **0,75 / 0,78** | 0,95 / **0,76** |

Xulosalar:

- **bge-m3 umuman eng yaxshi.** Ikkala to'plamda ham xom savollarda birinchi, `alt` bilan esa
  R@10 bo'yicha birinchi yoki ikkinchi. MRR bo'yicha (to'g'ri modda qanchalik yuqorida turishi)
  e5-small'dan 0,08–0,15 yuqori.
- **uzbek-e5-small'ning 1-to'plamdagi ustunligi tasodif edi.** 2-to'plamda u e5-small'dan
  yomonroq. Bu natija bitta, muallif yozgan savollar to'plamiga ishonib bo'lmasligini
  ko'rsatadi.
- **2-to'plamdagi hakam e5-small natijalarini tekshirgan** (4.5). Shunga qaramay bge-m3 va
  harrier e5-small'dan yuqori chiqdi, demak ularning ustunligi haqiqiy.
- **AI qayta yozganda farq kichrayadi:** R@10 bo'yicha 0,88–0,98. Ammo natijalar tartibida (MRR)
  farq saqlanadi, bu esa AI'ga beriladigan birinchi 3–5 ta natija sifatiga bevosita ta'sir
  qiladi.

To'liq korpus uchun narx. Taxmin: ≈22 ming hujjat, 300–700 ming bo'lak. Vektorlar `halfvec`da
saqlanadi, HNSW indeksi ustidan alohida joy oladi.

| Model | Vektorlar hajmi | Boshlang'ich embedding |
|---|---|---|
| e5-small (384) | 0,2–0,5 GB | Mac GPU ≈1 soat, `home` CPU (int8 ONNX) 4–8 soat |
| harrier-270m (640) | 0,4–0,9 GB | Mac GPU 6–14 soat |
| bge-m3 (1024) | 0,6–1,4 GB | Mac GPU 8–19 soat |

`myserver`da (3,7 GB RAM, boshqa ilovalar bilan umumiy) bge-m3 va uning indeksi xotiraga sig'ishi
qiyin. Bu model kuchliroq serverga o'tganda ma'qul keladi.

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

## 6a. 3-bosqich: bo'lak sarlavhalaridagi hujjat nomi (2026-11-06)

3-bosqichda hujjat nomi bir xil ko'rinishga keltirildi (`display_title`): "Qonun OʻRQ-637:
Taʼlim toʻgʻrisida" o'rniga endi "Taʼlim toʻgʻrisidagi Qonun (OʻRQ-637)" yoziladi. Nom har bir
bo'lak sarlavhasiga kiradi, shuning uchun 16 657 bo'lak qayta hisoblandi (Mac'da 8,5 daqiqa).
Natija sezilarli o'zgarmadi:

| To'plam | Oldin R@10 / MRR | Keyin R@10 / MRR |
|---|---|---|
| Qo'lda yozilgan 97 ta savol, LLM `alt` bilan | 0,91 / 0,56 | 0,90 / 0,57 |
| LLM yaratgan 100 ta savol, `alt` bilan | 0,88 / 0,63 | 0,88 / 0,63 |
| Qo'lda yozilgan 97 ta savol, xom | 0,70 / 0,36 | 0,71 / 0,37 |

Natija: `eval/results/2026-11-06-stage3-display-title.json`.

## 6b. Shovqinni kesish: past ballga ega natijalarni tashlash (2026-11-06)

**Savol.** 3-bosqichdagi Claude Code sinovida qidiruv ro'yxatining oxirida aloqasiz moddalar
chiqdi. Masalan, ishga tiklash muddati haqidagi savolga Jinoyat-protsessual kodeksidagi tergov
muddatlari chiqqan. Har bir ortiqcha natija ≈140 token oladi. Ularni ball bo'yicha olib tashlab,
to'g'ri moddani yo'qotmaslik mumkinmi?

**Usul** (`scripts/bench_cutoff.py`). Har bir savol uchun gibrid qidiruv bir marta bajarildi
(top 10). Keyin kesish qoidalari shu natijalar ustida hisoblandi. Tool odatda 8 ta natija
qaytaradi, shuning uchun ko'rsatkich R@8 va natijalar soni. Ikki qoida sinaldi:

- **A:** RRF bali eng yaxshi natija balining X foizidan past bo'lsa, natija tashlanadi.
- **B:** natija faqat bitta ro'yxatda va undagi o'rni pastda bo'lsa (>10, >20, >30), tashlanadi.

| To'plam | Kesishsiz R@8 | A 50 %: R@8 / natijalar soni / yo'qotilgan | A 60 % | A 70 % |
|---|---|---|---|---|
| Qo'lda yozilgan 97 ta, LLM `alt` | 0,85 | 0,84 / 7,4 / 1 | 0,84 / 6,4 / 1 | 0,80 / 4,9 / 4 |
| LLM yaratgan 100 ta, `alt` bilan | 0,87 | 0,87 / 7,4 / 0 | 0,84 / 6,5 / 3 | 0,82 / 4,7 / 5 |
| Qo'lda yozilgan 97 ta, xom | 0,64 | 0,64 / 7,4 / 0 | 0,62 / 6,5 / 2 | 0,57 / 5,6 / 7 |

B qoidasi deyarli hech narsani kesmadi. Birinchi 8 ta natijaning deyarli hammasi bir nechta
ro'yxatda chiqadi, shuning uchun natijalar soni 7,7–8,0 bo'lib qoldi.

Odatiy `limit`ni kamaytirish ham sinaldi:

| To'plam | R@5 | R@6 | R@8 | R@10 |
|---|---|---|---|---|
| Qo'lda yozilgan 97 ta, LLM `alt` | 0,78 | 0,80 | 0,85 | 0,90 |
| LLM yaratgan 100 ta, `alt` bilan | 0,82 | 0,84 | 0,87 | 0,88 |

**Xulosa: kesish foyda bermaydi, kod o'zgarmadi.**

- **Sababi.** Birinchi 8 ta natijaning RRF ballari bir-biriga juda yaqin, shuning uchun "shovqin"
  ballari bo'yicha boshqalaridan ajralib turmaydi. 50 % chegara atigi ≈7 % tokenni tejaydi va
  baribir bitta to'g'ri moddani yo'qotadi.
- **`limit`.** Uni 8 dan 6 ga tushirish R@ ni 0,05 ga kamaytiradi. Demak, hozirgi 8 to'g'ri.
  Sinovda shovqin aynan AI o'zi `limit=10` so'raganida ro'yxat oxirida chiqqan.
- **Haqiqiy yechim tartiblashni yaxshilash:** reranker modeli (masalan, `bge-reranker-v2-m3`)
  yoki kuchliroq embedding. Bu kuchliroq serverga o'tganda ko'riladi.

## 6c. To'liq bazada birinchi baholash (6-bosqich, 2026-11-10)

Baza: 15 810 amaldagi hujjat, shundan 10 432 tasi matni bilan indekslangan, 491 947 bo'lak
(avval 86 hujjat, 16 657 bo'lak). Model o'sha: `e5-small-int8`, HNSW m=32, ef_construction=200,
ef_search=100. Baholash Mac'dan SSH tunnel orqali server bazasida o'tkazildi (yangi kod:
`count(*)` keshi, `within`). Tunneldagi kechikish tufayli `ms` ustuni tezlikni ko'rsatmaydi.
Natija fayllari: `eval/results/2026-11-10-full-corpus-*.json`.

### Savollar to'plamlari

| Fayl | Savol | Qanday yaratilgan | `alt` |
|---|---:|---|---|
| `eval/questions.yaml` | 97 | qo'lda, kodeks va qonunlar (86 hujjat davri) | qo'lda yozilgan |
| `eval/questions_llm.yaml` | 100 | gpt-5.4, 86 hujjatdan, judged | yo'q (xom) |
| `eval/questions_decrees.yaml` | 29 | qo'lda, 11 ta qaror/farmon/buyruq, matnni o'qib | qo'lda yozilgan |
| `eval/questions_llm_full.yaml` | 300 | gpt-5.4, butun bazadan turlar bo'yicha, judged | yo'q (xom) |

`questions_llm_full`: tasodifiy hujjatdan bitta modda/band, hujjatlar turlar bo'yicha bazadagi
ulushiga qarab (`llm_eval.py generate --by-kind`). 1 355 ta band sinaldi, ≈75 %ini model
"oddiy fuqaro so'ramaydi" deb tashladi (tashkiliy bandlar). `judge` 175 ta savolga 231 ta
qo'shimcha to'g'ri javob qo'shdi. Turlar: vm_qarori 135, qaror 45, buyruq 36, boshqa 33,
qonun 25, farmon 19, kodeks 6, konstitutsiya 1. Kamchilik: ≈15 % savolda matndagi aniq raqam
yoki so'z bor (natijani biroz oshiradi). Tokenlar: generate ≈0,9 mln, judge ≈0,64 mln
(3 kalit bepul limiti tugagach `--allow-paid`).

`within`: qarorlarda band raqami takrorlanadi (qarorning o'zi va har bir Nizom), shuning uchun
kutilgan javob sarlavha yo'lining bir qismi bilan aniqlanadi (`evaluation.Expected.within`).

### Natijalar (R@10; qavsda 86 hujjatdagi qiymat)

> **Tuzatish (6d):** `questions_llm_full` va `questions_llm` qatorlaridagi raqamlar shishirilgan:
> `judge` qo'shgan javoblarning ko'pi noto'g'ri bo'lib chiqdi. Ishonchli qiymatlar 6d-bo'limda.

| To'plam | FTS | Vektor | Gibrid | Gibrid R@1 | Gibrid MRR |
|---|---:|---:|---:|---:|---:|
| questions, `alt` bilan (97) | 0,77 | 0,34 | **0,75** (0,92) | 0,34 | 0,47 |
| questions_llm, xom (100) | 0,29 | 0,08 | **0,26** (0,65) | 0,04 | 0,09 |
| questions_decrees, `alt` bilan (29) | 0,93 | 0,17 | **0,72** | 0,21 | 0,35 |
| questions_llm_full, xom (300) | 0,45 | 0,19 | **0,53** | 0,12 | 0,24 |

`questions_llm_full` gibrid R@10 turlar bo'yicha: vm_qarori 0,59 (135), buyruq 0,58 (36),
farmon 0,53 (19), boshqa 0,52 (33), qonun 0,48 (25), qaror 0,44 (45), **kodeks 0,00 (6)**,
konstitutsiya 0,00 (1). `questions` teglari bo'yicha: mehnat 0,73, oila 0,70, qonun 0,65,
soliq 0,67, pensiya 0,33, fuqarolik 0,87, jinoyat 0,75.

### Tashxis

- **Vektor qidiruv to'liq bazada deyarli ishlamaydi.** 8 ta `questions_llm` savolida HNSW va
  aniq (indekssiz) qidiruv solishtirildi: kerakli modda top-50 da ikkalasida ham faqat 1 tasida
  (19- va 22-o'rin). Demak sabab indeks emas, model: e5-small 490 ming o'xshash bo'lak
  ("…chora-tadbirlari toʻgʻrisida") orasida ma'noni ajrata olmaydi. HNSW aniq top-50 ning
  34–50 tasini topdi (kichik qo'shimcha yo'qotish).
- **Vektor shovqini gibridni pasaytiradi:** `questions_llm`da gibrid 0,26 < FTS 0,29;
  `questions_decrees`da gibrid 0,72 < FTS 0,93.
- **Kodekslar siqib chiqariladi:** kodeks moddalarini yuzlab qarorlardagi o'xshash bandlar
  ortga suradi (`questions_llm_full`da kodeks 0/6).
- Xom LLM savollarida `alt` yo'q; xizmatda AI qayta yozadi (86 hujjatda bu 0,65 → 0,90 bergan).

### Tezlik (serverda, issiq kesh, 8 savol, 1 ta `alt` bilan)

Gibrid: mediana 0,69 s, maksimum 0,94 s. Vektor ≈0,01 s, FTS 0,1–0,65 s (umumiy so'z ko'p bo'lakka
mos keladi, masalan 15 773 bo'lak). HNSW qurish: 7,5 daqiqa, 640 MB. Bo'sh RAM qurilgandan keyin
≈2,7 GB; tungi update'da 900 MB peak + ≈1 GB swap.

### Tuzatish variantlari (muhokama qilinadi, qaror qabul qilinmagan)

1. `rephrase` bilan 300 ta savolga AI `alt`ini yozish va real sharoitga yaqin o'lchash
   (≈0,3 mln token).
2. Hujjat turiga og'irlik: Konstitutsiya va kodekslar yuqoriroq, qonunlar o'rtada.
3. Gibridda vektor og'irligini kamaytirish, FTS nomzodlarini ko'paytirish (RRF parametrlari).
4. Qayta saralovchi model (reranker) top-50 da: sifat katta, lekin server CPU va javob vaqti.
5. Kuchliroq embedding (bge-m3: 86 hujjatda MRR +0,1): server RAM'ini oshirish kerak.

Tavsiya: 1 → 2 → 3, har biridan keyin to'rtala to'plamni qayta o'lchash; 0,85 ga yetmasa 4/5.
Ommaga ochish shu ish tugaguncha kechiktiriladi.

## 6d. Baholash to'plamini tozalash va ishonchli boshlang'ich nuqta (2026-11-10)

6c'dagi 1-variant bajarildi va u to'plamning o'zida uchta muammoni ochdi. Baza va model o'sha
(491 947 bo'lak, `e5-small-int8`). Hammasi `questions_llm_full` (300 savol) ustida.

**Qisqacha (2026-11-10/11):**

| Bosqich | Aniq savollar (208), R@10 | R@1 |
|---|---:|---:|
| Hozirgi gibrid qidiruv, tozalangan javoblar ro'yxati | 0,644 | 0,20 |
| Eng yaxshi birlashtirish sozlamasi (oflayn) | 0,678 | 0,23 |
| + yengil reranker, birinchi 30 ta | 0,755 | 0,41 |
| + og'ir reranker, birinchi 30 ta (CPU'da 30 s) | 0,769 | 0,50 |
| Nomzodlar to'plami chegarasi: 30 / 50 / butun to'plam | 0,78 / 0,82 / 0,93 | — |

Topilmalar:

1. LLM yozgan savollarning 31 %i (92/300) kontekstsiz, javobi aniqlab bo'lmaydi: `clarity`
   bilan ajratiladi va alohida hisoblanadi.
2. LLM `judge` qo'shgan javoblarning faqat 30 %i (114/386) haqiqiy: iqtibosli qat'iy tekshiruvsiz
   ishlatib bo'lmaydi. Avvalgi raqamlar shu sababli shishirilgan edi.
3. AI'ning rasmiy iboralari aniq savollarda foyda beradi, noaniqlarida zarar qiladi; savol matni
   ham kerak (usiz R@10 0,54).
4. Vektor qidiruv (`e5-small`) bu bazada deyarli ishlamaydi: topilmagan 74 savoldan 46 tasida
   to'g'ri modda vektorning 200 taligida ham yo'q.
5. O'rinlarga asoslangan birlashtirishni sozlash shovqin darajasida (+3 %). Matnni o'qiydigan
   qayta saralash ishlaydi; endi R@10 ni nomzodlar to'plami cheklaydi.

### 1. AI `alt`i bilan o'lchash

`llm_eval.py rephrase` har savolga 2 ta rasmiy qidiruv iborasini yozdi
(`eval/alt_llm_questions_llm_full.json`, ≈71 ming token). Natija kutilganidek chiqmadi: gibrid
R@10 0,53 → 0,54 (FTS 0,45 → 0,55, vektor 0,19 → 0,24). 49 ta savol topildi, 47 tasi yo'qoldi.
86 hujjatdagi "0,65 → 0,90" takrorlanmadi.

### 2. Noaniq savollar

Topilmagan 139 ta savoldan 40 tasi qo'lda ko'rildi: 14 tasida savolning o'zidan gap nima haqida
ekanini bilib bo'lmaydi. Sabab: `generate` bitta bandni kontekstsiz ko'rib savol yozadi. Masalan,
`lf-111`: "Men bir marta shu yordam pulini olgan bo'lsam, keyin yana topshirsam bo'ladimi?" —
manba tibbiyot xodimlarini qo'llab-quvvatlash haqidagi qaror, savolda esa tibbiyot so'zi yo'q.
86 hujjatda bu sezilmagan, 15 ming hujjatda bunday savolga o'nlab hujjat mos keladi.

`llm_eval.py clarity` (gpt-5.4 savolni va manba hujjat nomini ko'radi) har savolga `aniq` yoki
`noaniq` tegini qo'ydi: 208 aniq, 92 noaniq. `eval` hisobotida ikkala guruh alohida chiqadi.
Belgilash taxminiy: qo'lda "noaniq" deyilgan 14 tadan 9 tasida model ham shunday dedi, qo'lda
"aniq" deyilgan 26 tadan 4 tasini model noaniq dedi.

AI `alt`i aniq savollarda foyda beradi (gibrid 0,52 → 0,60), noaniq savollarda zarar qiladi
(0,54 → 0,39): 1-banddagi "o'zgarmadi" shu ikkisining yig'indisi edi. (Bu raqamlar hali eski,
shishirilgan javoblar ro'yxati bilan.)

### 3. `judge` juda yumshoq

`judge --alt-file --missed-in` aniq savollardagi 83 ta xatoning top-10 natijasini baholadi
(≈246 ming token) va 73 tasida "to'g'ri javob bor" dedi: qog'ozda R@10 0,95. Qabul qilinganlardan
15 tasi qo'lda o'qildi: 6 tasi to'g'ri, 3 tasi bahsli, 6 tasi noto'g'ri. Masalan, `lf-286`
("institutga ishga kirishda sinov darsi o'tishim shartmi?") uchun Mehnat kodeksining dastlabki
sinov muddati haqidagi 132-moddasi qabul qilingan.

Shuning uchun `judge` qo'shgan barcha 386 ta javob (6c'dagi 231 + bugungi 155) qat'iy qoida
bilan qayta tekshirildi: tekshiruvchi moddaning to'liq matnini o'qiydi va javob beradigan jumlani
so'zma-so'z ko'chirib ko'rsatadi, iqtibos matnda topilmasa javob o'chiriladi. Tekshiruvni Claude
subagentlari bajardi (6 ta, matnlar mahalliy `data/parsed`dan), iqtiboslar skript bilan tekshirildi.
Bu qadam `llm_eval.py` buyrug'i emas, natijasi `eval/verified_llm_full.json`da.

| Holat | Soni |
|---|---:|
| O'tdi (`verified: true`) | 114 |
| Rad etildi | 215 |
| Bahsli, o'chirildi | 8 |
| Matni mahalliy fayldan topilmadi (raqamsiz qism), o'chirildi | 49 |

6c'dagi birinchi `judge`ning 231 ta javobidan 53 tasi qoldi. Xulosa: `JUDGE_SYSTEM` (800–1200
belgi, faqat "ha/yo'q") javoblarning taxminan uchdan ikkisini noto'g'ri qabul qiladi, uning
natijasini iqtibos talabisiz ishlatib bo'lmaydi. `questions_llm.yaml` (100 savol) hali
tekshirilmagan.

### Ishonchli boshlang'ich nuqta

Tozalangan javoblar ro'yxati, AI `alt`i bilan
(`eval/results/2026-11-10-full-corpus-questions_llm_full-alt_llm-verified.json`):

| Guruh | Rejim | R@1 | R@5 | R@10 | MRR |
|---|---|---:|---:|---:|---:|
| aniq (208) | FTS | 0,23 | 0,47 | 0,60 | 0,34 |
| aniq (208) | vektor | 0,06 | 0,18 | 0,25 | 0,11 |
| aniq (208) | gibrid | 0,20 | 0,53 | **0,64** | 0,33 |
| noaniq (92) | gibrid | 0,04 | 0,23 | 0,26 | 0,11 |

Aniq savollarda gibrid R@10 turlar bo'yicha: qonun 0,77 (22), vm_qarori 0,67 (86), kodeks 0,67
(6), boshqa 0,65 (23), buyruq 0,63 (19), qaror 0,60 (35), farmon 0,44 (16).

- Uchala rejimdan kamida bittasi top-10 da topgan savollar: 0,70. Rejimlarni birlashtirishni
  sozlash bilan bundan oshib bo'lmaydi.
- 20 ta savolni faqat gibrid topdi, 11 tasini FTS topib, gibrid chiqarib yubordi.
- Ro'yxat qattiq tozalangani uchun 0,64 pastki baho: topilmagan savollarning ayrimlarida qidiruv
  ro'yxatda yo'q, lekin to'g'ri moddani topgan bo'lishi mumkin.

`eval`ga `--workers` (parallel qidiruv, har oqimga alohida ulanish) va jarayon ko'rsatkichi
qo'shildi: tunnel orqali 300 savol × 3 rejim (2 ta `alt` bilan) 4 oqimda ≈43 daqiqa, bitta oqimda
≈90 daqiqa.

### Topilmagan savollarda to'g'ri modda qayerda

`scripts/miss_depth.py`: gibrid topolmagan 74 ta aniq savol uchun to'g'ri moddaning o'rni
(savol va 2 ta `alt` bo'yicha eng yaxshisi, har ro'yxatda 200 talikkacha;
`eval/results/2026-11-10-full-corpus-miss-depth.json`). O'lchovda `ef_search` 400.

| Ro'yxat | 1–10 | 11–50 | 51–200 | yo'q |
|---|---:|---:|---:|---:|
| FTS (istalgan so'rov) | 29 | 17 | 16 | 12 |
| Vektor (istalgan so'rov) | 1 | 9 | 18 | 46 |
| Hozirgi birlashtirilgan ro'yxat (har ro'yxatdan 50) | 1 | 26 | 23 | 24 |

- **Birlashtirish yo'qotadi:** 29 ta savolda to'g'ri modda kamida bitta FTS ro'yxatining top-10
  ida turibdi, lekin RRF uni birlashtirilgan top-10 dan chiqarib yuborgan (6 ta ro'yxatning
  bir nechtasida uchraydigan o'rtacha nomzodlar bitta ro'yxatda yuqori turgan nomzoddan o'zib
  ketadi).
- **Nomzodlar bor, tartibi noto'g'ri:** 50 ta savolda to'g'ri modda hozirgi nomzodlar to'plamida
  (o'rtacha 218 modda) bor. Ideal qayta saralash bilan chegara: (134 + 50) / 208 = 0,88;
  nomzodlar 200 talikkacha kengaytirilsa (yana 16 ta) 0,96. 8 ta savolda 200 talikda ham yo'q.
- **Vektor deyarli yordam bermaydi:** 74 tadan 46 tasida to'g'ri modda vektor ro'yxatining
  200 taligida ham yo'q, top-50 da faqat 10 tasida bor.
- **Savolning o'zi ham kerak:** FTS top-50 da 18 ta savolni faqat savol matni, 21 tasini faqat
  `alt` topgan.

### Birlashtirish variantlari (oflayn)

`scripts/dump_candidates.py` 300 savolning 6 tadan nomzod ro'yxatini (har birida 200 ta) bir
marta `data/eval/candidates_llm_full.json.gz`ga yozadi; `scripts/fusion_lab.py` shu fayldan
birlashtirish variantlarini bazasiz hisoblaydi (butun to'r 15 soniya). Hozirgi qoidani fayldan
qayta hisoblash 0,649 berdi (serverda 0,644; farq `ef_search` 400 dan), ya'ni model to'g'ri.
208 ta aniq savol, gibrid:

| Variant | R@1 | R@5 | R@10 | MRR |
|---|---:|---:|---:|---:|
| hozirgi qidiruv | 0,20 | 0,53 | 0,649 | 0,33 |
| vektorsiz (faqat FTS) | 0,23 | 0,47 | 0,611 | 0,34 |
| savol matnisiz (faqat `alt`) | 0,20 | 0,45 | 0,543 | 0,30 |
| vektor og'irligi 0,5 | 0,21 | 0,56 | 0,663 | 0,35 |
| eng yaxshi: FTS'dan 100 nomzod, k=20, vektor og'irligi 0,5 | 0,23 | 0,57 | 0,678 | 0,38 |
| hujjat turi og'irligi (kodeks 1,5, qonun 1,2) eng yaxshi variant ustiga | 0,25 | 0,55 | 0,673 | 0,38 |

- O'rinlarga asoslangan hech bir qoida (og'irliklar, RRF doimiysi, bitta ro'yxatdagi eng yaxshi
  o'rin uchun bonus, modda darajasida birlashtirish, bitta hujjatdan ko'p nomzod chiqqani uchun
  bonus, hujjat turi) 0,68 dan oshmadi. +3 foiz 208 savolda 6 ta savol degani; savollarning ikki
  yarmi orasidagi farq esa 0,59 va 0,77, ya'ni bu yutuq shovqin chegarasida.
- Sabab: 6 ta ro'yxatning har birida o'z top-10 i bor, 10 ta o'ringa 60 tagacha nomzod da'vogar.
  Qaysi biri to'g'ri ekanini o'rinlar emas, matnning o'zi hal qiladi.
- Nomzodlar to'plamining chegarasi (to'g'ri modda to'plamda bor savollar ulushi): hozirgi
  (50 + 50) 0,885; FTS 100 + vektor 50 da 0,928; 200 + 200 da 0,962.
- Natijalar sonini oshirish kam beradi: eng yaxshi variantda R@20 0,74, R@30 0,78, R@50 0,82.
- Savol matni kerak (usiz 0,54), vektor ham ozgina foyda beradi (usiz 0,61).

Xulosa: 0,85 ga faqat nomzodlar matnini o'qiydigan qayta saralash (reranker) yoki kuchliroq
nomzod topish bilan yetiladi; birlashtirishni sozlash yetmaydi.

### Qayta saralash (reranker), oflayn (2026-11-10/11)

`scripts/dump_chunk_texts.py` nomzod bo'laklarning matnini (71 955 ta, 51 mln belgi)
`data/eval/chunk_texts_llm_full.json.gz`ga oladi. `scripts/rerank_lab.py score` eng yaxshi
birlashtirish variantining (FTS 100, k=20, vektor 0,5) birinchi N ta moddasini cross-encoder
bilan baholaydi ("savol matni + moddaning eng yaxshi bo'lagi", o'rtacha 190 token), `report`
qayta tartiblab o'lchaydi. Mashina: `home`, i5-1235U, GPU yo'q, torch CPU. 208 ta aniq savol.

| Model | N | R@1 | R@5 | R@10 | MRR | s/savol |
|---|---:|---:|---:|---:|---:|---:|
| reranker'siz | — | 0,23 | 0,57 | 0,678 | 0,38 | — |
| `mmarco-mMiniLMv2-L12-H384-v1` (118 mln) | 10 | 0,43 | 0,63 | 0,678 | 0,51 | 1,1 |
| | 20 | 0,40 | 0,67 | 0,731 | 0,52 | 2,1 |
| | 30 | 0,41 | 0,68 | 0,755 | 0,53 | 3,2 |
| | 50 | 0,41 | 0,71 | 0,760 | 0,53 | 5,3 |
| | 100 | 0,40 | 0,70 | 0,779 | 0,53 | 10,7 |
| `bge-reranker-v2-m3` (568 mln) | 10 | 0,49 | 0,66 | 0,678 | 0,56 | 10 |
| | 20 | 0,48 | 0,71 | 0,726 | 0,57 | 20 |
| | 30 | 0,50 | 0,74 | 0,769 | 0,59 | 30 |

N ≥ 20 qatorlari "aralash" tartib bilan: `1/(10 + reranker o'rni) + 0,5/(10 + birlashtirilgan
o'rin)`. Faqat reranker bahosi bilan R@10 0–5 foiz past. `gte-multilingual-reranker-base`
o'lchanmadi: modelning o'z kodi transformers 5.22 bilan `IndexError` beradi.

- Yengil model ham R@1 ni deyarli ikki baravar oshiradi (0,23 → 0,41), R@10 ni 0,68 → 0,76.
  U o'zbek tilida o'qitilmagan (mMARCO, 14 til).
- Og'ir model R@1 va R@5 da yaxshiroq (0,50 va 0,74), R@10 da deyarli teng (0,769): N=30 da
  to'plam chegarasi 0,784, ikkala model ham unga yaqin. R@10 ni endi reranker emas, nomzodlar
  to'plami cheklaydi (N=50 da chegara 0,82, N=100 da 0,85, butun to'plamda 0,93).
- Tezlik: yengil model 9,4 juftlik/s, og'ir model 1,0 juftlik/s. Og'ir model CPU'da xizmatga
  yaramaydi; yengil model uchun ham N=30 da 3,2 s (hozirgi qidiruv 0,7 s). Serverda va int8
  ONNX bilan o'lchanmagan.

### Keyingi qadam

1. Yengil reranker'ni xizmatga tayyorlash: int8 ONNX, N=20–30, serverda tezlikni o'lchash.
2. "Savol → modda" o'qitish to'plami (LLM yozgan, `clarity` va iqtibosli tekshiruvdan o'tgan) va
   unda embedding modelini hamda yengil reranker'ni qo'shimcha o'qitish: birinchisi nomzodlar
   to'plamini, ikkinchisi tartibni yaxshilaydi (7-bo'lim).

Maqsad o'zgarmagan: aniq savollarda R@10 ≥ 0,85, ommaga ochish shungacha kechiktiriladi.

## 6e. Tutuq belgisi va oʻ/gʻ shakli embedding uchun (2026-11-11)

Hujjatlar rasmiy shaklda saqlanadi: oʻ/gʻ uchun U+02BB, tutuq belgisi uchun U+02BC. FTS savolni
ham shu shaklga keltiradi va belgini olib tashlaydi. Vektor qidiruvda esa savol modelga yozilgan
holicha berilardi. LLM savollarida asosan U+2018 (638 ta), U+0027, U+2019 uchraydi, rasmiy
belgilar kam (80 ta). e5 tokenizer har bir belgini alohida token qiladi: `bo‘ladi` →
`bo` + `‘` + `ladi`.

Sinov: 208 ta aniq savol, har biri uchun gibrid birlashtirishning birinchi 100 ta bo'lagi
(`data/eval/`), e5-small int8. To'g'ri modda shu 100 talikda bo'lgan 177 ta savolda vektor
tartibi o'lchandi (savol va 2 ta `alt`dan eng yaxshisi). Bo'lak matni sarlavhasiz.

| Modelga beriladigan shakl (hujjat + savol) | 1-o'rin | Top 5 | Top 10 | O'rtacha o'rin |
|---|---:|---:|---:|---:|
| **Tipografik `‘` (U+2018) va `’` (U+2019)** | **55** | **117** | **142** | **6,8** |
| Avvalgi holat: hujjat rasmiy, savol yozilgandek | 46 | 107 | 137 | 8,0 |
| Oddiy `'` (U+0027) | 36 | 96 | 133 | 9,6 |
| Belgisiz | 33 | 99 | 129 | 9,5 |
| Rasmiy `ʻ` `ʼ` (U+02BB, U+02BC) | 27 | 88 | 134 | 9,7 |

Xulosa: e5 o'zbek tilini web matnidan o'rgangan, u yerda tipografik qo'shtirnoqlar ko'p, rasmiy
belgilar kam. Shuning uchun modelga (hujjat va savol) tipografik shakl beriladi:
`normalize.embedding_text`. Saqlanadigan matn, FTS va foydalanuvchiga ko'rsatiladigan matn
o'zgarmaydi. Model nomi `e5-small-int8/q1` bo'ldi, eski vektorlar qayta ishlatilmaydi. Butun
korpus `qonunshunos reembed --rebuild-hnsw` bilan qayta hisoblandi (`home`, 2026-11-11/12,
10,7 soat, 492 139 bo'lak; HNSW qayta qurish 19 daqiqa).

To'liq korpusda natija (208 ta aniq savol, LLM `alt`; FTS natijalari 300/300 savolda aynan bir
xil, ya'ni farq faqat vektordan):

| Rejim | R@1 | R@5 | R@10 | MRR |
|---|---:|---:|---:|---:|
| Vektor, oldin | 0,058 | 0,178 | 0,245 | 0,110 |
| Vektor, keyin | 0,101 | 0,284 | 0,370 | 0,176 |
| Gibrid, oldin | 0,202 | 0,534 | 0,644 | 0,332 |
| **Gibrid, keyin** | **0,245** | **0,562** | **0,668** | **0,375** |

Gibrid top-10: 8 ta savol qo'shildi, 3 tasi chiqib ketdi. Natija:
`eval/results/2026-11-12-full-corpus-questions_llm_full-alt_llm-q1.json`.

Yangi nomzodlar (`dump_candidates`, 2026-11-12; eskilari `data/eval/q0/`da) ustida oflayn
laboratoriyalar, 208 ta aniq savol, R@10 (qavsda q0, ya'ni avvalgi vektorlar bilan):

| Variant | R@1 | R@10 |
|---|---:|---:|
| Hozirgi qidiruv | 0,23 | 0,668 (0,644) |
| Eng yaxshi birlashtirish | 0,25 | 0,692 (0,678) |
| + yengil reranker, top 30, savol, blend 0,5 (`home`da ≈2,8 s) | 0,41 | 0,760 (0,755) |
| + yengil reranker, top 50, savol, blend 0,5 (≈4,7 s) | 0,41 | 0,769 |
| + yengil reranker, top 30, savol + 2 `alt` (≈8,5 s) | 0,39 | 0,774 |
| Nomzodlar chegarasi top 20 / 30 / 50 / hammasi | — | 0,764 / 0,788 / 0,822 / 0,947 (0,740 / 0,784 / 0,822 / 0,928) |

Reranker natijasi deyarli o'zgarmadi: u allaqachon top 30 chegarasiga (0,79) yaqin. Top 50 da ham
chegara 0,82, ya'ni faqat reranker bilan 0,85 ga yetib bo'lmaydi; birinchi bosqich (nomzodlar)
yaxshilanishi kerak. "halves" ustunida yarimlar orasidagi farq 0,15–0,20: 208 savolda ±0,02
farqlar shovqin.

## 7. Ochiq masalalar

- **Model tanlovi.** 4.7-bo'lim: sifat bo'yicha bge-m3 birinchi, lekin `myserver` uchun og'ir.
- **Haqiqiy foydalanuvchi savollari** hali yo'q. Xizmat ishga tushgach, so'rovlar anonim holda
  yig'ilib, baholash to'plamiga qo'shiladi.
- **Farmon va qarorlar:** `questions_decrees.yaml` (29, qo'lda) va `questions_llm_full.yaml`da
  bor (6c, 6d).
- **Yuridik domenga moslashtirish.** LLM yordamida yaratilgan "savol → modda" juftliklarida
  embedding modelini va yengil reranker'ni qo'shimcha o'qitish (fine-tuning). O'qitish
  juftliklari `clarity` va iqtibosli tekshiruvdan o'tishi kerak (6d); baholashdagi 208 savol va
  ularning manba moddalari o'qitishga kirmasligi kerak.
- **Reranker'ni xizmatga qo'yish:** int8 ONNX, N=20–30, serverda tezlik (6d).
- **`questions_llm.yaml` (100 savol)** hali `clarity` va qat'iy tekshiruvdan o'tmagan: uning
  `judge` javoblari ham shishirilgan deb hisoblash kerak.
- **`gte-multilingual-reranker-base`** transformers 5.22 bilan ishlamadi (modelning o'z kodi).

## Qayta ishlab chiqarish

```bash
uv run qonunshunos crawl-sample && uv run qonunshunos crawl --ids-file eval/corpus/laws.txt
uv run qonunshunos db-migrate && uv run qonunshunos index
uv run qonunshunos eval --alt-file eval/alt_llm.json
uv run qonunshunos eval --questions eval/questions_llm.yaml --alt-file eval/alt_llm_questions_llm.json
uv run --group bench python scripts/bench_embeddings.py --alt-file eval/alt_llm.json
# To'liq baza (6c): server bazasiga tunnel orqali, QONUNSHUNOS_DSN tunnelga qaratilgan
uv run python scripts/llm_eval.py generate --by-kind --sample 450 --limit 300 \
    --out eval/questions_llm_full.yaml --id-prefix lf --workers 6
uv run python scripts/llm_eval.py judge --questions eval/questions_llm_full.yaml --workers 6
uv run qonunshunos eval --questions eval/questions_llm_full.yaml --save full-corpus-questions_llm_full
# 6d: AI alt, aniq/noaniq teglari, ikkinchi judge (keyin javoblar eval/verified_llm_full.json
# bo'yicha tozalangan), tozalangan ro'yxat bilan o'lchash
uv run python scripts/llm_eval.py rephrase --questions eval/questions_llm_full.yaml \
    --out eval/alt_llm_questions_llm_full.json
uv run python scripts/llm_eval.py clarity
uv run python scripts/llm_eval.py judge --questions eval/questions_llm_full.yaml \
    --alt-file eval/alt_llm_questions_llm_full.json --depth 10 --chars 800 \
    --missed-in eval/results/2026-11-10-full-corpus-questions_llm_full-alt_llm.json
uv run qonunshunos eval --questions eval/questions_llm_full.yaml --workers 4 \
    --alt-file eval/alt_llm_questions_llm_full.json \
    --save full-corpus-questions_llm_full-alt_llm-verified
# Server bazasiga tunnel bilan: bash scripts/with_server_db.sh <buyruq> (oddiy terminalda)
bash scripts/with_server_db.sh uv run python scripts/miss_depth.py \
    --result eval/results/2026-11-10-full-corpus-questions_llm_full-alt_llm-verified.json \
    --alt-file eval/alt_llm_questions_llm_full.json \
    --out eval/results/2026-11-10-full-corpus-miss-depth.json
bash scripts/with_server_db.sh uv run python scripts/dump_candidates.py \
    --alt-file eval/alt_llm_questions_llm_full.json --out data/eval/candidates_llm_full.json.gz
bash scripts/with_server_db.sh uv run python scripts/dump_chunk_texts.py \
    data/eval/candidates_llm_full.json.gz --out data/eval/chunk_texts_llm_full.json.gz
# Oflayn (bazasiz)
uv run python scripts/fusion_lab.py data/eval/candidates_llm_full.json.gz
uv run --group bench python scripts/rerank_lab.py score \
    --model cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 --variants q --top 100
uv run --group bench python scripts/rerank_lab.py score \
    --model BAAI/bge-reranker-v2-m3 --variants q --top 30 --batch 8
uv run --group bench python scripts/rerank_lab.py report --tops 10 20 30 50 100
```
