# O'zbek tilidagi yuridik qidiruv: tajribalar jurnali

Nizom loyihasining 2-bosqichi (2026-11-05). Bu hujjatda o'zbek tilidagi qonun matnlari
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

**Tuzatish.** Mahalliy hisob qo'shildi ([llm.py](../src/nizom/llm.py),
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
korpus `nizom reembed --rebuild-hnsw` bilan qayta hisoblandi (`home`, 2026-11-11/12,
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

**Reranker xizmatga qo'yildi (2026-11-12).** int8 ONNX (`model_quint8_avx2.onnx`), birinchi 20 ta
birlik, faqat savol matni bilan, blend 0,5 (`search/rerank.py`, `NIZOM_RERANK_TOP`). Oflayn:
int8 fp32 dan farq qilmaydi (top 30 da R@10 0,750 va 0,760, R@1 0,42 va 0,41); matn shakli
(tipografik yoki rasmiy) ham farq qilmaydi. To'liq korpusda, jonli baza bilan:

| | Aniq (208): R@1 | R@5 | R@10 | MRR | Noaniq (92): R@1 | R@10 |
|---|---:|---:|---:|---:|---:|---:|
| Reranker'siz | 0,245 | 0,562 | 0,668 | 0,375 | 0,054 | 0,272 |
| **Reranker, top 20** | **0,394** | **0,649** | **0,716** | **0,502** | 0,174 | 0,293 |

Serverda (2 vCPU) issiq holatda bitta qidiruv `alt` bilan 4,6–5,2 s, reranker'siz 4,0–5,6 s:
asosiy vaqtni reranker emas, qidiruvning o'zi oladi. Xizmat jarayoni ikkala model bilan ≈1,1 GB.
Natija: `eval/results/2026-11-12-full-corpus-questions_llm_full-alt_llm-q1-rerank20.json`.

**Qidiruv vaqti (serverda, issiq kesh, savol + 1 `alt`).** Qismlarga bo'lindi: FTS 0,8–2,5 s, reranker
1,5–2,0 s, vektor 0,04–0,15 s, oxirgi so'rov ≈0,01 s. FTS vaqti mos kelgan chunk'lar soniga
bog'liq (6 ming → 0,2 s, 54 ming → 1,7 s): mos qatorlarni topish arzon (0,14 s), qimmati ball
hisoblash. Sinalgan va foyda bermagan: ballni `unnest(tsv)` bilan bir o'tishda hisoblash
(natija bir xil, 1,5–2 barobar sekinroq), FTS va vektor so'rovlarini parallel yuborish (2 vCPU'da
1,46 → 1,28 s). Reranker'ni 256 tokenga qisqartirish sifatni o'zgartirmadi (top 20: R@10 0,750,
R@1 0,413; 384 token: 0,740 / 0,404) va reranker vaqtini 1,1–1,5 s ga tushirdi; xizmatga qo'yildi.
Keyingi imkoniyat: `COMMON_DF` (5 %) ni pasaytirib FTS mos qatorlarini kamaytirish, eval bilan.

**Reranker'ga beriladigan matn shakli (2026-11-12, oflayn, int8, top 20, 512 token, blend 0,5,
208 aniq savol).** Savol va bo'lak tipografik `‘ ’` shaklda: R@1 0,404, R@5 0,688, R@10 0,740,
MRR 0,523. Rasmiy `ʻ ʼ` shaklda: 0,404 / 0,678 / 0,750 / 0,520. Farq shovqin darajasida, xizmat
tipografik shaklda qoladi (embedding bilan bir xil `embedding_text`).

## 6f. O'qitish to'plami: "savol → modda" juftliklari (2026-11-12)

Maqsad: e5-small (keyin reranker'ni ham) o'zbek qonunchiligiga moslashtirish, chunki 6e ga ko'ra
faqat reranker bilan 0,85 ga yetib bo'lmaydi. `scripts/train_data.py`:

- `export`: amaldagi hujjatlarning fuqaroga tegishli bo'laklari (kodeks/qonun moddalari, qaror
  ilovalaridagi nizom/tartib bandlari; yakunlovchi, o'tish davri, ijro qismlari va farmoyishlar
  chiqarib tashlanadi). Hujjat turi vazni: kodeks 8, konstitutsiya 4, qonun 3, buyruq 1,5.
  Barcha eval to'plamlaridagi hujjatlar (424 ta) chiqarib tashlanadi. Bir bo'lak ikki marta
  olinmaydi.
- `generate`: LLM har bir bo'lak uchun fuqaro savoli va rasmiy qidiruv iborasini yozadi yoki
  `skip` qiladi. Bo'lakning o'zi to'g'ri javob, shuning uchun `judge` kerak emas.
- `merge`: tekshiruv (≥3 so'z, kirill harfi yo'q, takror yo'q) va `data/train/pairs.jsonl`.

Holat (2026-11-12 oxiri): **796 juftlik**, 569 hujjatdan. Manba: `gpt-5.4` 415 (p001, b001–b008,
bepul limit, bo'laklarning ≈47 % ini qoldiradi), Claude Opus subagent'lari 360 (p001, c001–c010,
≈36 %), Sonnet 21 (pilot). 1 302 bo'lak `skip` qilindi, 2 tasi kirill harfi uchun tashlandi.
Savol medianasi 19 so'z, rasmiy ibora 7 so'z. Pilotda (p001, bir xil 100 bo'lak) Opus savollari
eng tabiiy edi, `gpt-5.4` savollari uzunroq.

Topilma: hujjat turlari bo'yicha `vm_qarori` 327, `qonun` 180, `buyruq` 154, `qaror` 47, `farmon`
32, `kodeks` atigi 9. Kodekslarning ko'pi eval hujjatlari sifatida chiqarib tashlangan, shuning
uchun vazn 8 ham yordam bermadi. Fine-tuning natijasi kodeks savollarida kuchsiz bo'lishi
mumkin; eval'ni hujjat turi bo'yicha ham ko'rish kerak.

Keyingi qadam: har kuni bepul `gpt-5.4` bilan ≈8 batch (b009 dan), kerak bo'lsa Opus batch'lari;
taxminan 1 500–2 000 juftlikda e5-small'ni fine-tune qilib, 208 aniq savolda o'lchash (796 bilan
sinov tariqasida ham boshlash mumkin).

Holat (2026-11-17): **1 849 juftlik**. `gpt-5.4` 1 146 (b001–b023, faqat bepul limit), Opus
subagent'lari 682 (c001–c022), Sonnet 21. c011–c022 da Opus bo'laklarning faqat ≈26 % ini qoldirdi:
o'zgartirish ro'yxatlari va idoralarning ichki vakolatlari ko'paydi. Jami 2 895 bo'lak `skip`
qilindi (≈60 %). Narx: bitta `gpt-5.4` batch (100 bo'lak) ≈69k kirish + ≈5,5k chiqish token,
pullik tarifda ≈$0,25 va ≈50 juftlik; 6 ta Opus batch foydalanuvchining Claude 5 soatlik
limitining ≈12 % ini oladi.

## 6g. e5-small'ni fine-tune qilish (2026-11-15..17)

`scripts/finetune_e5.py`: oddiy torch tsikli, in-batch negatives (MultipleNegativesRankingLoss
kabi, scale 20), har bir juftlikdan ikki misol (fuqaro savoli va rasmiy ibora → bo'lak), bir
batch'da bitta bo'lak ikki marta uchramaydi. Word embedding matritsasi (og'irliklarning 80 %)
muzlatilgan. Matn shakli xizmatdagidek (`embedding_text`, `query: ` / `passage: `). `home` CPU'da
batch 32 × 256 token 5,6 GB'da OOM bo'ldi; gradient checkpointing bilan ≈2,5 GB.

**ft1:** 1 506 juftlik (3 012 misol), 2 epoch, lr 2e-5, 190 qadam, `home` CPU'da 68 daqiqa, loss
2,40 → 0,07.

Baholash (`scripts/vector_lab.py`): butun korpus emas, saqlangan nomzodlar pool'i
(`dump_chunk_texts.py --heading`: barcha savollarning FTS top 100 va vector top 50 bo'laklari,
sarlavhasi bilan, 72 533 bo'lak). Har bir model pool'ni va savollarni embedding qiladi, vector
ro'yxatlarini o'zinikiga almashtiradi, FTS ro'yxatlari o'zgarmaydi; RRF `fusion_lab.py` bilan,
reranker'siz. 208 aniq savol:

| Run | R@1 | R@5 | R@10 | MRR |
|---|---|---|---|---|
| Saqlangan ro'yxatlar (xizmatdagi int8, butun korpus), hybrid | 0,231 | 0,538 | 0,668 | 0,366 |
| Base e5-small (fp32), vector | 0,106 | 0,298 | 0,385 | 0,187 |
| **ft1 (fp32), vector** | **0,250** | **0,582** | **0,697** | **0,390** |
| Base e5-small (fp32), hybrid | 0,216 | 0,572 | 0,688 | 0,367 |
| **ft1 (fp32), hybrid** | **0,365** | **0,673** | **0,769** | **0,500** |

Eval hujjatlari (424) o'qitishdan chiqarib tashlangan. Ehtiyot: pool korpusdan ≈7 barobar kichik,
to'liq korpusdagi raqam pastroq bo'lishi mumkin; reranker qo'shilmagan (xizmatda reranker'siz
hybrid 0,668, reranker bilan 0,716).

**Serverga moslash (`scripts/export_onnx.py`).** Server faqat ONNX o'qiydi (torch'siz).
- TorchScript eksportchisi `transformers` 5 ning mask kodini misol shakliga bog'lab qo'ydi: fp32
  ONNX vektorlarining torch bilan cosine'i 0,93. Dynamo eksportchisi bilan 1,0000.
- Oddiy int8 (`quantize_dynamic`, bitta scale): cosine 0,93. Xizmatdagi base int8 fayl o'z fp32
  si bilan 0,984 beradi. `per_channel=True` bilan ft1 int8 0,98 (fayl o'sha 119 MB).
- int8 ft1 pool'da (`home`, ≈5 soat: onnxruntime arena'si har xil shakllar uchun 5,7 GB gacha
  o'sgani uchun `vector_lab.py` da o'chirilgan, ≈4 bo'lak/s): hybrid R@10 **0,774** (R@1 0,356),
  vector 0,668. fp32 bilan farq shovqin darajasida (hybrid 0,769), demak serverga int8 yetadi.

`home` CPU'da bitta tajriba ≈1 kun olgani uchun keyingi tajribalar ijaradagi GPU'da (RunPod)
bo'ladi: 750 / 1 506 / 1 849 juftlik (ko'proq data foyda beradimi), int8 va fp32 masalasi,
2–3 ta sozlama varianti. Butun korpusni qayta embedding qilish `home` CPU'da 10,7 soat (6e).

## 6h. GPU'da fine-tune tajribalari (RunPod, 2026-11-18)

RunPod Secure Cloud, RTX 3090 24 GB, EU-CZ-1, $0,50/soat (`get-capacity` $0,22 ko'rsatgan edi,
bu Community narxi). Pod ≈68 daqiqa ishladi, ≈$0,57. `finetune_e5.py` va `vector_lab.py` CUDA
bo'lsa GPU'da ishlaydi (GPU'da gradient checkpointing o'chiq). Bitta o'qitish (1 849 juftlik,
2 epoch) ≈40 s (`home` CPU'da 68 daqiqa), pool'ni (72 533 bo'lak) embedding qilib baholash ≈3
daqiqa (`home`da int8 ≈5 soat).

Baholash 6g dagidek: pool, 208 aniq savol, fp32, reranker'siz. Bitta savol = 0,005.

**Data hajmi** (2 epoch, batch 32, lr 2e-5, seed 7). 1 506 to'plami ft1 niki (b017–b023
batch'larining bo'laklari chiqarilgan), 753 uning tasodifiy yarmi (seed 7):

| Juftlik | hybrid R@1 | hybrid R@10 | vector R@10 |
|---|---|---|---|
| 0 (base) | 0,216 | 0,688 | 0,385 |
| 753 | 0,365 | 0,774 | 0,688 |
| 1 506 | 0,370 | 0,779 | 0,692 |
| 1 849 | 0,365 | 0,793 | 0,707 |

Data ikki barobar bo'lganda +1 savol: bu hajmda data asosiy cheklov emas. GPU'dagi 1 506
(0,779) CPU'dagi ft1 ga (0,769) yaqin.

**Sozlamalar** (1 849 juftlik):

| Run | hybrid R@1 | hybrid R@10 | vector R@10 |
|---|---|---|---|
| 2 epoch, b32, lr 2e-5 | 0,365 | 0,793 | 0,707 |
| batch 64 | 0,375 | 0,779 | 0,712 |
| batch 128 | 0,380 | 0,764 | 0,692 |
| 4 epoch, lr 3e-5, seed 7 | 0,375 | 0,822 | 0,707 |
| 4 epoch, lr 3e-5, seed 8 | 0,380 | 0,841 | 0,731 |
| 4 epoch, lr 3e-5, seed 9 | 0,394 | 0,808 | 0,721 |
| 4 epoch, lr 5e-5 | 0,356 | 0,832 | 0,721 |
| **6 epoch, lr 3e-5, seed 7 (`e6`)** | 0,389 | **0,837** | **0,760** |
| 6 epoch, lr 3e-5, seed 8 | 0,356 | 0,822 | 0,736 |
| 8 epoch, lr 3e-5 | 0,389 | 0,827 | 0,764 |
| 10 epoch, lr 3e-5 | 0,380 | 0,837 | 0,750 |

Xulosalar:
- Seed shovqini katta: bir xil sozlamada R@10 0,808–0,841 (±3–4 savol). Bitta run'ga ishonma.
- Kattaroq batch foyda bermadi. Uzunroq o'qitish bergan: 2 epoch 0,793, 4–10 epoch 0,81–0,84,
  4 epoch'dan keyin to'yinadi.
- Tanlov: `e6` (6 epoch, lr 3e-5, batch 32, seed 7), `home`da `data/models/gpu1/e6` (yana
  `gpu1/e4s8`). Keyingi qadam: int8 eksport, butun korpusni qayta embedding qilish (GPU'da) va
  xizmatda reranker bilan o'lchash.

## 6i. Butun korpusni GPU'da qayta embedding qilish (2026-11-18)

**Tokenizer xatosi.** transformers fine-tune'dan keyin `tokenizer.json`ga oxirgi chaqiruv
sozlamalarini yozadi (`padding: BatchLongest`, pad_id 1; `truncation: 256`). `Embedder`
`encode_batch` natijasidagi hamma id'larni matn deb hisoblardi: vektor batch'dagi eng uzun
matnga bog'liq bo'lib qolgan (bitta matn yolg'iz va 32 talik batch'da: e6 fp32 ONNX cosine
0,54–1,0; Xenova fayllari 1,000 / int8 0,996). torch va ONNX bir xil batch'da 1,0000 bergani
uchun `export_onnx.py` tekshiruvi buni ko'rmagan. Tuzatildi: `load_tokenizer` (padding o'chiq,
truncation 512), eksport toza `tokenizer.json` yozadi. Tuzatishdan keyin e6 fp32 1,000, int8
0,98–0,99. **6g dagi ft1 int8 pool natijasi (0,774) shu xato bilan o'lchangan.**

**Embedding.** `dump_chunk_texts.py --all --heading` (492 263 bo'lak, 69 MB) →
`scripts/embed_file.py --torch` (fp32, RunPod RTX PRO 6000, Secure, US-KS-2, $2,69/soat;
`get-capacity` $1,69 ko'rsatgan): ≈1 500 bo'lak/s, butun korpus ≈5,5 daqiqa (`home` CPU'da
int8 10,7 soat). int8 ONNX GPU'da ishlamadi (onnxruntime-gpu 1.32 CUDA 13 + cuDNN 9 so'radi va
CPU'ga tushdi, 4 thread'da 14 bo'lak/s). Pod ≈27 daqiqa, ≈$1,2.

Pool baholashi butun korpus vektorlaridan (`vector_lab.py --model NAME@vectors.npz`, 40 ta pool
bo'lagi faylda yo'q, korpus o'zgargan), 208 aniq savol, reranker'siz:

| Bo'laklar | Savollar | hybrid R@1 | hybrid R@10 | vector R@10 |
|---|---|---|---|---|
| e6 fp32 | e6 fp32 (torch) | 0,389 | 0,837 | 0,760 |
| e6 fp32 | e6 int8 ONNX | 0,380 | 0,837 | 0,745 |

Qaror: bo'laklar fp32 bilan (GPU), savollar serverda int8 bilan. Hybrid natija bir xil,
server xotirasi o'zgarmaydi. Vektorlar: `home`da `data/embed/e6-fp32/vectors.npz` (ids,
float16).

**Deploy (2026-11-18).** Xizmat modeli `e5-small-e6-int8/q1` (`index/embed.py`, fayllar HF'da emas,
`deploy.sh` `home`dan ko'chiradi). `scripts/load_vectors.py` serverda: HNSW o'chirildi, 492 263
vektor 20 000 talik batch'larda yozildi (COPY → UPDATE, 218 s), 10 274 hujjat belgilandi,
`reembed` uchun hujjat qolmadi; HNSW qayta qurildi (≈29 daqiqa, 2 yadro).

**Xizmatda o'lchov** (butun korpus, `nizom eval --rerank`, 208 aniq savol, LLM `alt`):

| Run | R@1 | R@5 | R@8 | R@10 | MRR |
|---|---|---|---|---|---|
| q1 (eski), reranker'siz | 0,245 | 0,562 | 0,654 | 0,668 | 0,375 |
| q1 (eski), rerank 20 (avvalgi xizmat) | 0,394 | 0,649 | 0,688 | 0,716 | 0,502 |
| e6, reranker'siz | 0,389 | 0,697 | 0,760 | 0,793 | 0,515 |
| **e6, rerank 20 (xizmat)** | **0,462** | **0,764** | **0,841** | **0,846** | **0,586** |
| e6, faqat vector | 0,236 | 0,558 | 0,630 | 0,663 | 0,370 |

FTS natijalari o'zgarmadi (R@10 0,601), farq faqat vektordan. R@8 ham ko'rsatildi: `search_law`
standart holatda 8 ta modda qaytaradi. Maqsad (R@10 0,85) bilan farq ≈1 savol. Pool natijasi
(0,837, reranker'siz) butun korpusda 0,793 bo'ldi.

## 6j. Lemma, birlashtirish, fine-tune qilingan reranker (2026-11-18/19)

**FTS lemmatizatsiyasi.** O'zbek tili uchun ochiq vositalar sinaldi (UzbekStemmer,
UzMorphAnalyser, uzbek-morph, Apertium asosidagi uzmorph). Eng yaxshisi uzmorph (GPL-3.0), lekin
u ham unli tushishida (shahri), "-uvchi" va inkor "-ma" da xato qiladi. Xizmatda uzmorph kodi
ishlamaydi: `scripts/build_lemmas.py` korpusdagi 230 ming so'z uchun "so'z → lemma" jadvalini
bir marta tuzadi, paketga faqat o'zagi o'zgaradigan 9 081 so'z (`text/lemmas.tsv.gz`) kiradi.
Qoidalar: fe'llar (UPOS VERB/AUX) lemmalanmaydi (solinadigan → sol bo'lib ketardi); ma'noni
o'zgartiradigan qo'shimchalar lemmada qoladi (-li, -siz, -uvchi, -chi, -lik, -ma, -ov);
FTS so'zi = `stem(lemma)`, shunda jadvalda yo'q shakllar ham bir o'zakka tushadi; "-chi"ning
"i"si egalik deb kesilmaydi; shahr → shahar kabi 10 ta unli tushishi qo'lda. Xizmatda (e6,
eski reranker, top 20): FTS R@1 0,231 → 0,250, R@5 0,466 → 0,505, R@10 0,601 → 0,596; gibrid
R@10 0,846 → 0,832 (±3 savol, shovqin chegarasida). Lemma qoldirildi: keyingi qadamlar shu
nomzodlar ustida tanlandi.

**Tutuq belgilari.** FTS'da ʻ ʼ olib tashlanadi; korpusda shu sabab bir-biriga qo'shilib ketadigan
sezilarli juftliklar 123 ta (so'z qo'llanishlarining 0,5 %): bosh/boʻsh, oʻlim/olim, daʼvo/davo.
Embedding va reranker belgilarni ko'radi, shuning uchun o'zgartirilmadi.

**Oflayn tahlil** (`data/eval/v2/`: xizmatdagi nomzodlar, 300 savol, chuqurlik 200; 208 aniq):
- Birlashtirish: vektor kuchaygani uchun uning og'irligi oshirildi. Eng yaxshisi vektor
  ro'yxatidan 100 nomzod, og'irlik 1,5, RRF k=20, moddaning qo'shimcha bo'laklari uchun bonus
  yo'q: reranker'siz R@10 0,784 → 0,817. Nomzodlar chegarasi: top 20 da 0,870, top 30 da 0,899.
- `COMMON_DF` 5 % → 2 %: nomzodlar chegarasi deyarli o'zgarmadi (top 30: 0,904 → 0,899), FTS
  bitta so'rovda 0,8–2,5 s dan 0,04–0,2 s ga tushdi.

**Reranker fine-tune** (`scripts/mine_negatives.py`, `scripts/finetune_reranker.py`, RunPod RTX 5090,
$1,39/soat, ≈45 daqiqa ≈ $1). Har bir juftlikning savoli va rasmiy iborasi uchun e6 bilan butun
korpusdan eng yaqin 30 bo'lak (o'z moddasidan tashqari) hard negative. mmarco-mMiniLMv2, guruh
(1 to'g'ri + 7 yoki 15 manfiy) bo'yicha cross-entropy, 2 epoch, ≈1 daqiqa. Yangi birlashtirish,
reranker faqat savol matnini o'qiydi, blend 0,5:

| Reranker | top 20: R@1 | R@10 | top 30: R@1 | R@5 | R@10 |
|---|---|---|---|---|---|
| asl mmarco | 0,50 | 0,856 | 0,50 | 0,77 | 0,851 |
| rr1 (guruh 8) | 0,57 | 0,861 | 0,57 | 0,83 | 0,875 |
| rr1, seed 8 / 3 epoch / lr 3e-5 | 0,55–0,59 | 0,856–0,865 | 0,56–0,57 | 0,83–0,84 | 0,880–0,885 |
| **rr3g16 (guruh 16)** | 0,58 | 0,865 | 0,56 | 0,84 | **0,889** |
| rr3g16 int8 ONNX | 0,54 | 0,870 | 0,54 | 0,84 | 0,889 |

Sarlavha bilan o'qitilgan reranker yomonroq (top 30: 0,865), savol + `alt` iboralarning
eng yaxshi bahosi ham (0,861). e5 ni hard negative'lar bilan qayta o'qitish (e7) pool'da
yomonlashtirdi (hybrid 0,803 → 0,745): mined negative'lar orasida javoblar ko'p, e6 qoldi.

**Xizmatga** (2026-11-19): reranker `mmarco-uz-rr1-int8` (fayllar HF'da emas, `home`dagi
`data/models/local__mmarco-uz-rr1`, `scripts/export_reranker.py`; dynamo eksport, int8 per channel;
eksportchining value_info'si kvantlashda shape xatosi beradi, olib tashlanadi), top 30, yangi
birlashtirish, `COMMON_DF` 2 %, HNSW `ef_search` 200. Reranker matnlarni uzunligi bo'yicha
4 tadan baholaydi (padding kam): 30 ta modda serverda ≈2,2 s → ≈1,4 s. Qidiruv reranker'siz
≈0,3 s, jami ≈2–3 s (avval 3–4 s). To'liq eval 43 → 26 daqiqa.

**Xizmatdagi o'lchov** (butun korpus, 300 savol, LLM `alt`, gibrid):

| Run | aniq R@1 | R@5 | R@8 | **R@10** | MRR | noaniq R@10 |
|---|---|---|---|---|---|---|
| e6 + eski FTS + asl reranker top 20 | 0,462 | 0,764 | 0,841 | 0,846 | 0,586 | 0,489 |
| e6 + lemma + asl reranker top 20 | 0,471 | 0,769 | 0,822 | 0,832 | 0,589 | 0,511 |
| **e6 + lemma + yangi birlashtirish + rr3g16 top 30** | **0,538** | **0,822** | **0,865** | **0,875** | **0,655** | **0,576** |

Maqsad (aniq savollarda R@10 ≥ 0,85) bajarildi. Ehtiyot: birlashtirish va reranker sozlamalari
shu 208 savolda tanlangan; savollarning ikki yarmida natija yaqin (0,85/0,92).

## 6k. Halol o'lchov: dev/test va "ko'r" savollar (2026-11-19)

**Muammo.** 0,875 optimistik bo'lishi mumkin: (1) savollar moddani ko'rib yozilgan, so'zlari
moddaga yaqin; (2) fine-tune juftliklari ham, baholash savollari ham GPT-5.4 dan, bir xil
ko'rsatma bilan; (3) birlashtirish va reranker sozlamalari o'sha 208 savolda tanlangan;
(4) `judge` faqat bizning qidiruv topganini ko'rgan.

**Dev/test.** `llm_eval.py split` 300 savolni har (aniqlik, hujjat turi) guruhida teng ikkiga
bo'ldi (`dev`/`test` teglari, seed 2026): har birida 150 savol, 104 tasi `aniq`. Bundan keyin
sozlash faqat dev'da (`fusion_lab`, `rerank_lab`, `vector_lab`, `miss_depth` standart holatda
`--tag aniq,dev`), test faqat o'lchanadi. `nizom eval` `aniq+dev`, `aniq+test` ni alohida
chiqaradi. Joriy xizmat (6j) natijasi qismlar bo'yicha:

| | n | R@1 | R@5 | R@8 | R@10 |
|---|---|---|---|---|---|
| aniq, dev | 104 | 0,548 | 0,827 | 0,885 | 0,894 |
| aniq, test | 104 | 0,529 | 0,817 | 0,846 | **0,856** |

Test ham o'tgan sozlashlarda ishlatilgan, shuning uchun 0,856 ham to'liq toza emas: toza raqam
faqat bundan keyingi o'zgarishlar uchun.

**"Ko'r" savollar** (`eval/questions_blind.yaml`, 120 ta, `scripts/blind_eval.py`):
- **Yozish.** 4 ta Claude (Opus) subagent hech narsa qidirmasdan, faqat hayotiy vaziyatlardan
  savol yozdi: har biriga boshqa sohalar (mehnat/pensiya, oila/meros/uy-joy, soliq/tadbirkorlik/
  transport, ta'lim/sog'liq/harbiy/javobgarlik), har xil personajlar, uchdan biri "real"
  imlo bilan (tutuq belgisiz, "prava", "propiska").
- **Javobni belgilash.** 8 ta boshqa subagent bizning qidiruvni ishlatmadi: butun korpus
  (15 810 hujjat, 419 586 birlik, `data/eval/blind/units.tsv.gz`) ustida regex `grep`, nom
  bo'yicha qidiruv va mundarija bilan topdi, har birini to'liq o'qib tasdiqladi. 1–6 ta javob
  (o'rtacha ≈3), hammasiga javob topildi. Raqamsiz ilova jadvallari (`matn`) `article: ""` bilan
  hisoblanadi (`evaluation.Expected`).
- **O'qitish bilan kesishish.** 2 ta savolning javob moddasi fine-tune juftliklarida bor
  (`trained` tegi). Juftliklar baholash hujjatlarini chetlab o'tgani uchun kam.
- **Kamchiliklar.** Belgilashning boshida `grep`da tutuq belgisi xatosi bor edi (3 ta
  belgilovchiga ta'sir qilgan bo'lishi mumkin): o'tkazib yuborilgan javoblar natijani pasaytiradi,
  oshirmaydi. Bitta model oilasi (Claude) yozgan, savollar ko'pincha ikki qismli.
- `alt`: 300 savoldagi kabi `llm_eval.py rephrase` (GPT-5.4, ≈32 ming token).

**Natija** (xizmatdagi qidiruv: e6 + lemma FTS + `mmarco-uz-rr1`, top 30, LLM `alt`):

| | R@1 | R@5 | R@8 | R@10 |
|---|---|---|---|---|
| qat'iy: faqat mustaqil belgilar | 0,408 | 0,667 | 0,767 | 0,800 |
| + top-10 dagi javoblar, hakam tasdiqlagan | 0,458 | 0,775 | 0,883 | **0,917** |
| solishtirish: 300 to'plam, aniq, test | 0,529 | 0,817 | 0,846 | 0,856 |

- **Hakam.** Topilmagan 24 savolning top-10 matnini 2 ta subagent qat'iy mezon bilan ko'rdi va
  14 savolda 26 ta to'g'ri moddani tasdiqladi (`judged: true`). Ulardan bir nechtasi aniq asosiy
  javob, belgilovchi esa uni o'tkazib yuborgan: Mehnat kodeksi 230 (yillik ta'til), FK 551 (ijara
  shartnomasini muddatidan oldin bekor qilish), Bola huquqlari kafolatlari qonuni 14 (bolani chet
  elga olib chiqish), PQ-99 (jarimani 15/30 kunda to'lashda chegirma). Shuning uchun qat'iy 0,800
  pastki chegara. 0,917 esa yuqori chegara: hakam faqat bizning qidiruv topganini ko'rgan.
  300 to'plamdagi 0,856 ham shunday `judge` bilan o'lchangan, ya'ni 0,917 bilan solishtiriladi.
- **Xulosa.** Moddani ko'rmay yozilgan savollarda natija **yomonlashmadi**. Shubha (1)–(2)
  tasdiqlanmadi: model GPT uslubiga moslashib qolmagan. Sabab, ehtimol, odamlar ko'p so'raydigan
  mavzular (kodekslar, asosiy qonunlar) 300 to'plamdagi tasodifiy VM qarori bandlaridan osonroq.
  Javob topilmagan 10 savoldan 3 tasida korpusda to'liq javob yo'q (A-22, C-15, D-23). Haqiqiy
  xatolar: mehnat shartnomasining yozma shakli (A-12), chet elga ishga ketish (A-28),
  Toshkentda ro'yxatga olish (B-19), yakka uy qurish ruxsati (B-24), kassasiz savdo jarimasi (C-11),
  muddati o'tgan guvohnoma (C-25), murojaatga javob muddati (D-26).
- **Sohalar bo'yicha** (qat'iy R@10): uy-joy 0,44, tadbirkorlik 0,50, javobgarlik 0,50 eng past.
  Pensiya, sog'liq, meros va harbiy sohalarda 1,00.
- 120 savol kam: ±0,03–0,04 shovqin. Natija fayli:
  `eval/results/2026-11-19-full-corpus-questions_blind-alt_llm-rr1-top30.json`.

## 6l. Yurist javob bergan savollar: advice.uz (2026-11-23)

**Manba.** advice.uz ("Madad" NNT, bepul yuridik maslahat portali): savol shaklidagi maqolalar va
bo'limlardagi "Savol-javoblar" to'plamlari. Savollarni yurist tahrir qilgan (tili rasmiyroq), lekin
mavzular odamlar haqiqatan so'raydigan narsalar. Boshqa manbalar: buxgalter.uz (javoblar pullik,
ko'chirish taqiqlangan, 2019 yil, eski Mehnat kodeksi) yaramadi; gov.uz FAQ modullari kam
to'ldirilgan (5 ta idoradan 29 savol).

**Yig'ish va belgilash** (`scripts/real_eval.py`). 77 bo'lim, 202 sahifa (2 s oraliq). 390 savol,
COVID karantini (2054) va vaksina (2468) to'plamlari chiqarildi: 279. 10 ta subagent yurist
javobini ishora sifatida olib, javob moddalarini korpusdan `blind_eval.py grep/show` bilan
topdi (bizning qidiruv ishlatilmadi). Eskirgan javoblarda amaldagi qoida belgilandi. 10 savol
tushib qoldi (yuridik emas yoki korpusda qoida yo'q): **269 savol**, 16 tasi `trained`.
Savol va javob matnlari `data/`da qoladi, git'da faqat ID, URL va belgilar
(`eval/labels_advice.yaml`). `alt`: `llm_eval.py rephrase` (GPT-5.4, ≈62 ming token).

**Natija** (xizmatdagi qidiruv, 6j sozlamalari):

| | R@1 | R@5 | R@8 | R@10 |
|---|---|---|---|---|
| qat'iy | 0,454 | 0,725 | 0,792 | 0,829 |
| + top-10 dagi javoblar, hakam tasdiqlagan | 0,498 | 0,833 | 0,914 | **0,952** |

- Hakamlar 46 topilmagan savoldan 33 tasida top-10 da to'g'ri modda topdi. Bu yerda ular
  yumshoqroq: ko'p savol umumiy ("Pensiya bilan nafaqaning farqi nimada?",
  "Konstitutsiya to'g'ridan-to'g'ri amal qiladimi?") va bir nechta modda javob bo'la oladi.
  Haqiqiy qiymat 0,83 va 0,95 orasida.
- **Uch mustaqil to'plam bir xil manzarani beradi:** qat'iy R@10 0,80–0,83, hakam bilan
  0,92–0,95; 300 to'plamning testi (0,856, hakam bilan o'lchangan) ulardan pastroq. Ya'ni
  0,875 optimistik emas edi: qiyin qismi tasodifiy VM qarori bandlari, odamlar ko'p so'raydigan
  mavzular osonroq.
- **Aniqlik** (`llm_eval.py clarity`, GPT-5.4, manba = birinchi javob hujjati): 44 savol
  `noaniq`, asosan to'plamlardan ajratilgan kontekstsiz savollar ("Shartnoma qancha muddatga
  tuziladi?" — mavzu, uy-joy ijarasi, faqat to'plam sarlavhasida). Teglar `eval/labels_advice.yaml`da.

| advice.uz | n | R@1 | R@5 | R@8 | R@10 | R@10, hakam bilan |
|---|---|---|---|---|---|---|
| aniq | 225 | 0,493 | 0,764 | 0,836 | **0,876** | 0,964 |
| noaniq | 44 | 0,250 | 0,523 | 0,568 | 0,591 | 0,886 |

- **"Uy-joy zaif" asosan to'plam xatosi edi.** 15 uy-joy savolidan 8 tasi 2788-to'plamning
  kontekstsiz savollari (`noaniq`). `aniq` uy-joy savollarida qat'iy R@10 6/8. Haqiqiy xatolar
  alohida-alohida: shartnomasiz ijara uchun javobgarlik (MJtK 159¹), kvartira sotilganda ijara
  (FK 604), "ko'r" to'plamda Toshkentda ro'yxatga olish (yangi OʻRQ-1074 o'rniga chet elliklar
  haqidagi VM 593) va yakka uy qurish ruxsati. Test to'plamlarida sozlanmadi.
- **Hujjat nomlari tuzatildi.** Belgilovchilar payqadi: 32 ta qonunning amaldagi tahriri lex.uz'da
  faqat uni "yangi tahrirda" bayon qilgan o'zgartirish qonuni nomi bilan bor (Prokuratura, Banklar,
  Markaziy bank, Murojaatlar, Valyutani tartibga solish va boshqalar). Endi ular
  "Prokuratura toʻgʻrisidagi Qonun (257-II tahririda)" deb nomlanadi (`doctype.restated_title`),
  nom bo'lak sarlavhalariga ham kiradi. Serverda 30 tasi qayta indekslandi (matn `home`dagi bilan
  bir xil ekani `content_hash` bilan tekshirildi). Qolgan 2 tasi (Savdo-sanoat palatasi -3815461,
  O'simliklar karantini -3815502) serverda **matnsiz** edi: to'liq yuklashda minor=Y va
  "o'zgartish…" nomli aktlar faqat rekvizitlar bilan saqlanadi, tungi yangilanish ham shunday
  qoldiradi. Endi `index_document` butun aktni yangi tahrirda bayon qilgan aktni har doim to'liq
  indekslaydi; ikkalasi qayta indekslandi. Matnsiz saqlangan 5 371 aktdan boshqasi bunday emas
  (20+ birlikli 580 tasi haqiqiy o'zgartirish aktlari).

## 6m. lex.uz'ning o'z qidiruvi bilan solishtirish (2026-11-24)

**Usul** (`scripts/lexuz_search_eval.py`). 208 ta aniq savol (`questions_llm_full`), lex.uz'dagi "Milliy qonunchilik"
ro'yxatining "Matndagi so'z yoki jumla" filtri (`query_1` maydoni, "Aniq mos kelishi" belgilanmagan;
sahifa JS'i uni `/uz/search/nat?lang=4&status=Y&query=…` ga aylantiradi, 100 belgidan uzun matnni
qabul qilmaydi). Saytda alohida umumiy qidiruv oynasi yo'q. So'rovlar `myserver`dan, 2,5 s
oraliq bilan (4 × 208 = 832 ta). lex.uz modda emas, hujjat qaytaradi, shuning uchun mezon
yengilroq: kutilgan hujjatlardan biri birinchi 10 natija (birinchi sahifa, 20 tadan 10 tasi)
ichida bo'lsa yetarli. So'rov 100 belgigacha qisqartirildi (lex.uz cheklovi), tinish belgilari
olib tashlandi, apostroflar lex.uz yozuviga (oʻ, gʻ, ʼ) keltirildi. To'rt variant: savol matni,
AI'ning birinchi rasmiy iborasi (`alt`), shu iboraning birinchi 2 va 3 so'zi.

**lex.uz qidiruvi qanday ishlaydi** (sinov so'rovlaridan): so'rovdagi hamma so'z bor hujjatlarni
topadi (aniq so'z shakli bilan) va ularni sana bo'yicha, eng yangisidan tartiblaydi. Masalan,
"yillik mehnat taʼtili" so'rovida 34 ta hujjat chiqdi, Mehnat kodeksi birinchi 5 tasida yo'q.

| So'rov | Natija qaytdi | R@1 | R@10 (hujjat) |
|---|---:|---:|---:|
| savol matni | 0,000 | 0,000 | 0,000 |
| rasmiy ibora | 0,043 | 0,005 | 0,019 |
| iboraning 2 so'zi | 0,981 | 0,034 | 0,120 |
| iboraning 3 so'zi | 0,856 | 0,038 | 0,159 |
| *Nizom, xizmat (modda, 6j)* | — | *0,538* | *0,875* |

Natija: `eval/results/2026-11-24-lexuz-search.jsonl` (faqat ID'lar). Uzun so'rovda lex.uz deyarli
hech narsa topmaydi ("Sizning so'rovingiz bo'yicha hujjat topilmadi!"). Qisqa so'rovda natija bor,
lekin saralanmagan. Kalit so'zlarni qo'lda yaxshiroq tanlagan odam bundan yuqori natija olishi
mumkin: bu raqamlar oddiy qoida bilan tanlangan so'zlar uchun.

## 6n. Stemmer va lemmaning ta'siri, butun korpusda (2026-11-24)

**Usul** (`scripts/fts_ablation.py`). 4.1'dagi stemming o'lchovi 21 hujjat va 77 savolda edi, 6j'dagi
lemma o'lchovi esa faqat lemmani solishtirgan. Bu safar uch holat bir xil sharoitda o'lchandi:
- `none`: so'z faqat `fold` qilinadi (kichik harf, tutuq belgilarisiz), stemming yo'q;
- `stem`: lemma jadvaligacha bo'lgan stemmer (d7d1c2d: `-chi` qoidasi va unli tushishi yo'q);
- `lemma`: xizmatdagi holat (f0160c4).

Baza: `home`da sudo'siz ochilgan alohida PostgreSQL 18 klaster (port 5441), unga 2026-11-23 kechki
zaxira nusxadan faqat `documents`, `sections`, `chunks`, `fts_stats` tiklandi. `home`da pgvector
yo'q, shuning uchun `embedding` matn sifatida tiklandi va `vector_candidates` numpy'dagi aniq
cosine qidiruv bilan almashtirildi (HNSW emas). Qolgan hamma narsa `nizom eval` yo'li:
IDF FTS, RRF, `mmarco-uz-rr1-int8` top 30. Har variant uchun `tsv` va `fts_stats` qayta qurildi.
208 ta aniq savol, LLM `alt`. Tekshiruv: `lemma` holati xizmatdagi o'lchovni takrorladi (FTS R@10
0,630, reranker bilan 0,875 va R@1 0,538, 6j bilan bir xil).

| Holat | FTS so'zlari | FTS R@1 | FTS R@10 | Gibrid R@10 | + reranker R@1 | + reranker R@10 |
|---|---:|---:|---:|---:|---:|---:|
| `none` | 260 906 | 0,139 | 0,428 | 0,760 | 0,529 | 0,870 |
| `stem` | 166 969 | 0,250 | 0,615 | 0,812 | 0,529 | 0,885 |
| `lemma` | 162 053 | 0,264 | 0,630 | 0,817 | 0,538 | 0,875 |

Savolma-savol (top-10 ga kirgan / chiqib ketgan): FTS `none → stem` +53/−14, `stem → lemma` +6/−3;
gibrid `none → stem` +14/−3; reranker bilan `none → stem` +8/−5, `stem → lemma` +1/−3.

**Xulosa.** Stemmer FTS uchun katta foyda (R@10 +0,19), reranker'siz gibridda ham sezilarli
(+0,05). Reranker bilan farq shovqin ichida: vektor va reranker so'z shaklini o'zi tushunadi.
Lemma stemmer ustiga shovqin darajasida. 4.1'dagi "stemming shovqin darajasida" xulosasi kichik
to'plamdan chiqqan edi: butun korpusda FTS uchun bu noto'g'ri. Natijalar:
`eval/results/2026-11-24-fts-ablation-{none,stem,lemma}.json`.

## 7. Ochiq masalalar

- **Model tanlovi.** 4.7-bo'lim: sifat bo'yicha bge-m3 birinchi, lekin `myserver` uchun og'ir.
  Fine-tune qilingan e5-small (6h, 6i) va reranker (6j) bilan maqsad bajarildi.
- **Haqiqiy foydalanuvchi savollari** hali yo'q. Xizmat ishga tushgach, so'rovlar anonim holda
  yig'ilib, baholash to'plamiga qo'shiladi. 6j sozlamalari 208 savolda tanlangan edi; mustaqil
  to'plamlarda (6k, 6l) natija tasdiqlandi. Bundan keyin sozlash faqat `dev` qismida.
- **Farmon va qarorlar:** `questions_decrees.yaml` (29, qo'lda) va `questions_llm_full.yaml`da
  bor (6c, 6d).
- **Noaniq savollar** (92 ta, kontekstsiz): R@10 0,576. Ular uchun qidiruv emas, savolni
  aniqlashtirish (klient LLM `alt_queries` yozishi) yordam beradi.
- **Qidiruv tezligi:** 2–3 s, asosiy vaqt reranker (30 ta modda ≈1,4 s, 6j). FTS 0,04–0,2 s.
- **Ko'proq o'qitish juftliklari:** embedding uchun data hajmi asosiy cheklov emas (6h); reranker
  uchun sinalmagan. Hard negative'lar e5 ni yomonlashtirdi (6j).
- **FTS mayda xatolari:** "burni" → `bur` (-ni tushum kelishigi deb kesiladi); ba'zi so'zlar ichida
  boshqa tutuq belgisi bo'lgani uchun "toʻ", "boʻ" kabi yarim so'zlar indekslangan (6j).
- **`questions_llm.yaml` (100 savol)** hali `clarity` va qat'iy tekshiruvdan o'tmagan: uning
  `judge` javoblari ham shishirilgan deb hisoblash kerak.
- **`gte-multilingual-reranker-base`** transformers 5.22 bilan ishlamadi (modelning o'z kodi).

## Qayta ishlab chiqarish

```bash
uv run nizom crawl-sample && uv run nizom crawl --ids-file eval/corpus/laws.txt
uv run nizom db-migrate && uv run nizom index
uv run nizom eval --alt-file eval/alt_llm.json
uv run nizom eval --questions eval/questions_llm.yaml --alt-file eval/alt_llm_questions_llm.json
uv run --group bench python scripts/bench_embeddings.py --alt-file eval/alt_llm.json
# To'liq baza (6c): server bazasiga tunnel orqali, NIZOM_DSN tunnelga qaratilgan
uv run python scripts/llm_eval.py generate --by-kind --sample 450 --limit 300 \
    --out eval/questions_llm_full.yaml --id-prefix lf --workers 6
uv run python scripts/llm_eval.py judge --questions eval/questions_llm_full.yaml --workers 6
uv run nizom eval --questions eval/questions_llm_full.yaml --save full-corpus-questions_llm_full
# 6d: AI alt, aniq/noaniq teglari, ikkinchi judge (keyin javoblar eval/verified_llm_full.json
# bo'yicha tozalangan), tozalangan ro'yxat bilan o'lchash
uv run python scripts/llm_eval.py rephrase --questions eval/questions_llm_full.yaml \
    --out eval/alt_llm_questions_llm_full.json
uv run python scripts/llm_eval.py clarity
uv run python scripts/llm_eval.py judge --questions eval/questions_llm_full.yaml \
    --alt-file eval/alt_llm_questions_llm_full.json --depth 10 --chars 800 \
    --missed-in eval/results/2026-11-10-full-corpus-questions_llm_full-alt_llm.json
uv run nizom eval --questions eval/questions_llm_full.yaml --workers 4 \
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
# 6h–6j: GPU (RunPod) — fine-tune, butun korpus embedding, reranker
uv run --group bench python scripts/finetune_e5.py --out data/models/e6 --epochs 6 --lr 3e-5
uv run --group bench python scripts/export_onnx.py data/models/e6
bash scripts/with_server_db.sh uv run python scripts/dump_chunk_texts.py --all --heading \
    --out data/embed/chunk_texts_all.json.gz
uv run --group bench python scripts/embed_file.py data/embed/chunk_texts_all.json.gz \
    --torch data/models/e6 --out data/embed/e6-fp32 && \
    uv run python scripts/embed_file.py --out data/embed/e6-fp32 --merge
venv/bin/python scripts/load_vectors.py data/embed/e6-fp32-vectors.npz   # serverda
PYTHONPATH=src /tmp/uzm/.venv/bin/python scripts/build_lemmas.py \
    data/embed/chunk_texts_all.json.gz --out data/fts/lemmas.tsv \
    --package src/nizom/text/lemmas.tsv.gz             # uzmorph + lt-proc kerak
venv/bin/nizom index --fts-only                        # serverda, ≈1 soat
bash scripts/with_server_db.sh uv run python scripts/dump_candidates.py \
    --alt-file eval/alt_llm_questions_llm_full.json --out data/eval/v2/candidates.json.gz
uv run --group bench python scripts/mine_negatives.py --vectors data/embed/e6-fp32/vectors.npz \
    --chunks data/embed/chunk_meta.npz --model data/models/e6 --out data/train/negatives.jsonl
uv run --group bench python scripts/finetune_reranker.py --negatives data/train/negatives.jsonl \
    --texts data/embed/chunk_texts_all.json.gz --out data/models/rr3g16 --group 16 --batch 8
uv run --group bench python scripts/rerank_lab.py score --candidates data/eval/v2/candidates.json.gz \
    --texts data/eval/v2/texts.json.gz --cache data/eval/v2/rr_text \
    --fusion n_vec=100,k=20,w_vec=1.5,extra_chunks=0.0 --model data/models/rr3g16 --top 50
uv run --group bench python scripts/export_reranker.py data/models/rr3g16
```
