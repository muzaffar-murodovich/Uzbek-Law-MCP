# 6-bosqich: to'liq yuklab olish va bepul ommaga ochish

Holat (2026-11-08): to'liq yuklab olish `myserver`da ketyapti (pastda "Bajarilganlar va
dizayndan farqlar"). Indekslash, baholash va ommaga ochish hali oldinda. Tegishli hujjatlar:
[PLAN.md](../PLAN.md) (1-, 2- va 8-bo'limlar), [lex.uz tadqiqoti](research/lexuz.md) (6-, 8.4- va
9-bo'limlar), [1-bosqich](stage1-parser-crawler.md) (crawler), [5-bosqich](stage5-ops.md) (tungi
yangilash, zaxira nusxa).

## Maqsad

Hozir bazada 86 ta hujjat bor: Konstitutsiya, 20 ta kodeks va 65 ta qonun. Farmon va qarorlar
yo'q. Odamlar esa ko'pincha farmon, qaror va idoralar hujjatlarida yozilgan narsalarni so'raydi:
BHM miqdori, pensiya tartibi, litsenziya, davlat boji. Bu bosqichda:

1. **To'liq yuklab olish.** MVP qamrovidagi barcha amaldagi hujjatlar (≈22 ming) lex.uz'dan
   yuklab olinadi, parse qilinadi va indekslanadi. Kuchini yo'qotganlarining (≈12 ming) faqat
   rekvizitlari saqlanadi.
2. **Tungi yangilash butun qamrovga kengaytiriladi:** yangi farmon va qarorlar ham indeksga
   qo'shiladi.
3. **Qidiruv sifati qayta o'lchanadi.** Hujjatlar 250 baravar ko'payadi, kodeks moddalari
   minglab qarorlar orasida "ko'milib" qolmasligi kerak.
4. **Ommaga ochish:** `robots.txt`, huquqshunos tasdig'i, bosh sahifa matni, e'lon.

Oddiy qilib aytganda: hozirgacha kutubxonaning bitta javonini (kodekslar) to'ldirib, katalogni
sinab ko'rdik. Endi butun kutubxonani olib kelamiz. Kitoblarni bittadan, shoshmasdan tashiymiz
(lex.uz'ni qiynamaslik uchun), keyin katalog hamon kerakli kitobni topayotganini tekshiramiz.

## Hozirgi holat (2026-11-07 da tekshirildi)

- `myserver`: 2 vCPU, 3,7 GB RAM (≈2,2 GB bo'sh), diskda 25 GB bo'sh. Baza 182 MB:
  86 hujjat, 16 657 bo'lak (≈11 KB bitta bo'lakka, indekslar bilan birga).
- `home`: 12 yadro, 7,4 GB RAM, `/media/muzaffar/Data`da 204 GB bo'sh. `data/raw` 11 MB.
- Embedding tezligi: 16 657 bo'lak Mac'da 8,5 daqiqada, ya'ni ≈33 bo'lak/s.
- lex.uz statistikasi (2026-11-05): MVP qamrovidagi 4 toifada ≈34 400 lotin hujjat, shundan
  ≈22 mingtasi amalda. Toifalar: qonun hujjatlari, Prezident hujjatlari, hukumat qarorlari,
  vazirlik va idoralar hujjatlari.
- Ro'yxatlar hozir faqat shakl bo'yicha olinadi (`fform_id`, sahifada 20 ta). Shakl va toifa
  bir-biriga to'g'ri kelmaydi: "Qaror" shaklida Prezident, Vazirlar Mahkamasi va hokimlarning
  qarorlari aralash keladi. Toifa filtri hali o'rganilmagan.
- Tungi `update` faqat `konstitutsiya` va `kodeks` turidagi yangi hujjatlarni qo'shadi
  (`SCOPE_KINDS`). Navbat bilan tekshirish kechasiga 400 ta so'rov bilan cheklangan.

## Hajm va vaqt hisobi

| Ish | So'rovlar | Vaqt (2 s/so'rov) | Natija hajmi |
|---|---:|---:|---|
| Ro'yxatlar (≈34 400 qator, 20 tadan) | ≈1 750 | ≈1 soat | `data/listings/`, bir necha MB |
| Sinov to'plami (300 ta tasodifiy hujjat) | ≈600 | ≈20 daqiqa | — |
| Amaldagilar: matn + kartochka (≈22 000 × 2) | ≈44 000 | ≈25 soat | `data/raw` ≈2–4 GB (gzip) |
| Kuchini yo'qotganlar: faqat ro'yxat qatori | 0 | — | rekvizitlar jadvali |
| Embedding (≈0,5 mln bo'lak, `home`) | — | ≈4–5 soat | vektorlar ≈0,4 GB |

Jami ≈27 soat yuklab olish, ya'ni 2 kecha va 1 kun. Xatolar va qayta urinishlar bilan
3 kun deb rejalashtiramiz.

Baza: ≈0,5 mln bo'lak × ≈11 KB ≈ **5–6 GB**. Diskka sig'adi (25 GB bo'sh), lekin zaxira nusxa
bilan muammo bor (pastda "Zaxira nusxa").

## Qamrov

PLAN.md'dagi MVP qamrovi o'zgarmaydi:

| Toifa | Kiradi | Izoh |
|---|---|---|
| Qonun hujjatlari | ✅ | Konstitutsiya, kodekslar, qonunlar, Oliy Majlis qarorlari |
| Prezident hujjatlari | ✅ | farmon (PF), qaror (PQ), farmoyish |
| Hukumat qarorlari | ✅ | Vazirlar Mahkamasi qarorlari va farmoyishlari |
| Vazirlik va idoralar hujjatlari | ✅ | Adliya vazirligida ro'yxatga olingan buyruq va nizomlar |
| Mahalliy hokimiyat, xalqaro, sud amaliyoti va boshqalar | keyin | 7-bosqichdan keyin |

- Faqat lotin versiyasi (manfiy ID) yuklanadi.
- **Amaldagi** hujjat to'liq yuklanadi: matn va kartochka.
- **Kuchini yo'qotgan** hujjat uchun faqat ro'yxat qatori saqlanadi: nomi, organ, sana va raqam
  (`.badge`dan), holati. **Taklif:** kartochkani yuklamaslik. Bu ≈12 ming so'rovni (≈7 soat)
  tejaydi. Kuchini yo'qotgan sanasi kerak bo'lsa, `get_document` chaqirilganda kartochkani
  bitta so'rov bilan keyin olish mumkin.
- Faqat PDF'li hujjat (`pdf_only`) bazaga rekvizit sifatida yoziladi va tungi yangilashda
  qayta tekshiriladi (1-bosqichdagi qoida).

## Qanday ishlaydi

```
home                                                     myserver
────                                                     ────────
1. listing  ─► data/listings/<toifa>-<yil>.json
2. crawl    ─► data/raw/{docs,cards}/*.html.gz   (lex.uz, 2 s, davom ettirsa bo'ladi)
3. parse    ─► data/parsed/*.json
4. index    ─► embedding (home CPU) ─► SSH tunnel ─► PostgreSQL (qonunshunos)
5. requisites (kuchini yo'qotganlar) ─────────────► documents (status = lost_force)
```

### 1. Ro'yxatlar

- Avval kichik tadqiqot (≈30 so'rov): lex.uz qidiruvida **toifa** filtri bormi (statistika
  sahifasidagi toifalar qanday parametr bilan ochiladi)? Bo'lsa, ro'yxatlar toifa bo'yicha
  olinadi. Bo'lmasa, shakl (`fform_id`) bo'yicha olinadi va organ `.badge`dan aniqlanadi:
  hokimlik qarorlari tashlab yuboriladi.
- Ro'yxat **yil bo'yicha** bo'lib olinadi (`fyear`). Sabab: har bir keyingi sahifa oldingi
  sahifaning `__VIEWSTATE`iga bog'liq. 500 sahifalik zanjir o'rtada uzilsa, boshidan boshlash
  kerak bo'ladi. Yil bo'yicha zanjirlar qisqa va har biri alohida faylga saqlanadi: tugagan
  yil qayta yuklanmaydi.
- Natija: har bir qator — `lex_id`, nomi, `.badge`, holati, toifa.
- Tekshiruv: har bir toifadagi qatorlar soni lex.uz statistikasi bilan solishtiriladi (±2%).

### 2. Sinov to'plami (to'liq yuklashdan oldin)

Hozirgi parser 86 ta hujjatda sinalgan. 22 mingta hujjatda biz ko'rmagan tuzilmalar
uchraydi: ilovadagi jadvallar, sxemalar, faqat rasm, g'alati raqamlash. Shuning uchun:

- Har bir toifa va o'n yillikdan teng ulush bilan 300 ta tasodifiy amaldagi hujjat yuklanadi.
- Parse qilinadi va hisobot chiqadi: xato bilan tugaganlar, birorta modda/band topilmaganlar,
  matni juda qisqalar, `pdf_only`, kartochkada turi aniqlanmaganlar (`boshqa`).
- **Chegara:** xatolar <1% va bo'sh matn <3% bo'lmaguncha to'liq yuklab olish boshlanmaydi.
  Yangi uchragan tuzilmalar `tests/fixtures/`ga qo'shiladi.

### 3. To'liq yuklab olish (`crawl`)

Mavjud `qonunshunos crawl --ids-file` asosida, lekin uzoq ishga moslashtiriladi:

- **Davom ettirsa bo'ladi.** Allaqachon saqlangan sahifa qayta yuklanmaydi (bu hozir ham shunday).
  To'xtatib qayta ishga tushirilsa, qolgan joyidan davom etadi.
- **Tartib:** muhimroq hujjatlar avval: qonun hujjatlari → Prezident → hukumat → idoralar,
  har birida yangisi avval. Ish yarmida to'xtasa ham, eng kerakli qismi tayyor bo'ladi.
- **Tezlik o'zgarmaydi:** 2 soniyada 1 ta so'rov, parallel so'rov yo'q. lex.uz 429/5xx qaytarsa
  yoki ketma-ket 10 ta xato bo'lsa, 10 daqiqa kutadi. Bir soatda 50 tadan ko'p xato bo'lsa,
  to'xtaydi va Telegram'ga xabar yuboradi.
- **Tungi `update` bilan to'qnashmasin.** U `myserver`dan, crawl esa `home`dan lex.uz'ga so'rov
  yuboradi. Ikkalasi birga ishlasa, lex.uz bizdan soniyasiga 1 ta so'rov oladi. **Taklif:** crawl
  `update` ishlaydigan vaqtda (≈02:00–02:30) pauza qiladi. Buning o'rniga `update`ni shu
  kunlarga o'chirib qo'yish ham mumkin, lekin bu o'zgarishlarni o'tkazib yuborish xavfini tug'diradi.
- **Kuzatish:** har 6 soatda Telegram'ga holat keladi: nechta yuklandi, nechta qoldi, xatolar soni,
  tugash vaqti taxmini. Log `data/crawl-full.log`ga yoziladi.
- `home`da `systemd-run --user` bilan ishga tushiriladi, terminal yopilsa ham to'xtamaydi.

### 4. Indekslash

- Embedding `home`da hisoblanadi, natija SSH tunnel orqali to'g'ridan-to'g'ri `myserver`
  bazasiga yoziladi (CLAUDE.md'dagi qaror). Hujjatlar 100 tadan, bitta tranzaksiyada yoziladi.
  Xizmat shu paytda ishlashda davom etadi va yangi hujjatlar asta-sekin qidiruvda ko'rina boshlaydi.
- **HNSW indeksi.** 0,5 mln qatorni indeks bor jadvalga birma-bir qo'shish sekin va RAM'ni ko'p
  yeydi. Shuning uchun HNSW indeksi o'chirib turiladi, yozib bo'lingandan keyin bir marta
  qayta quriladi (`maintenance_work_mem = 1GB`, ≈20–40 daqiqa). Shu vaqt ichida vektor qidiruv
  sekinlashadi, FTS esa ishlayveradi. Buni tunda qilamiz.
- Indekslash ham davom ettirsa bo'ladigan bo'ladi: `content_hash` o'zgarmagan hujjat o'tkazib
  yuboriladi (bu hozir ham shunday).
- Oxirida `refresh_fts_stats` va `ANALYZE`.

### 5. Kuchini yo'qotganlar

Ro'yxat qatoridan `documents`ga `status = 'lost_force'` bilan yoziladi, bo'laklarsiz. Buning
uchun `index` buyrug'iga rekvizitlarni yozish rejimi qo'shiladi. Tool'lar bunday hujjatni
qidiruvda ko'rsatmaydi, lekin `find_document` "kuchini yo'qotgan" deb javob beradi.

## Tungi yangilash: nima o'zgaradi

- `SCOPE_KINDS` butun qamrovga kengaytiriladi. RSS'dagi yangi hujjat qamrovda bo'lsa (turi va
  organi bo'yicha), u yuklanib, indeksga qo'shiladi.
- **Navbat bilan tekshirish.** Hozir har bir hujjat kamida haftada bir marta tekshiriladi.
  22 ming hujjat va kechasiga 400 ta so'rov bilan bitta aylanish ≈55 kun davom etadi. Buni
  qabul qilamiz, chunki asosiy yo'l boshqa: o'zgartirish kirituvchi hujjat RSS'da chiqadi va u
  havola qilgan hujjatlar o'sha kechasi tekshiriladi. Navbat — faqat sug'urta. Navbatda
  kodekslar va qonunlar haftada bir marta, qolganlari navbat bilan tekshiriladi.
- Ertalabki hisobotga "qamrovdagi yangi hujjatlar: N" qatori qo'shiladi.

## Qidiruv sifati

Hujjatlar ko'paygani sari "Mehnat ta'tili qancha?" savolida Mehnat kodeksi o'rniga biror
vazirlik nizomidagi o'xshash jumla chiqishi mumkin. Shuning uchun:

- Baholash to'plamiga ≈30 ta yangi savol qo'shiladi: farmon, qaror va idoralar hujjatlaridagi
  qoidalar bo'yicha (BHM, eng kam ish haqi, davlat boji, litsenziya, pensiya).
- Eski 2-bosqich savollari (kodekslar bo'yicha) to'liq bazada qayta o'lchanadi. **Chegara:**
  R@10 0,85 dan pastga tushmasligi kerak.
- Tushsa, avval hujjat turiga qarab og'irlik beramiz (kodeks va qonun > farmon > idora
  hujjati) va `search_law`ga `doc_kind` filtrini qo'shamiz. Natijalar `docs/stage2-experiments.md`ga
  yoziladi.
- Bazaning javob vaqti o'lchanadi: `search_law` p95 1 soniyadan oshmasligi kerak.

## Zaxira nusxa

Hozir dump 41 MB, 14 kun saqlanadi. To'liq bazada dump ≈1,5–2 GB bo'ladi (vektorlar yaxshi
siqilmaydi), 14 ta nusxa ≈25 GB, ya'ni server diskiga sig'maydi. **Taklif:**

- Serverda faqat oxirgi 3 kunlik nusxa qoladi (`deploy/backup.sh`da hozir 14). `home`da
  hozir 30 kunlik saqlanadi, bu ≈60 GB bo'ladi. Uni 14 kunga tushiramiz (≈28 GB).
- Embedding'larni zaxira nusxasiz ham qayta hisoblash mumkin (≈5 soat). Lekin
  foydalanuvchilar va OAuth jadvallarini qayta tiklab bo'lmaydi. Shuning uchun ular har
  kecha alohida, kichik dump bilan saqlanadi.
- `home`dagi `~/backups` asosiy diskda turibdi, u yerda 34 GB bo'sh. Bu 28 GB'ga yetmaydi,
  shuning uchun nusxalar `/media/muzaffar/Data`ga ko'chiriladi (204 GB bo'sh).

## Ommaga ochish

To'liq baza tayyor bo'lib, sifat tekshirilgandan keyin:

1. **`robots.txt`** (bizning saytda): bosh sahifa, `/maxfiylik`, `/shartlar` ochiq; `/mcp`,
   `/auth/*` va OAuth manzillari (`/authorize`, `/token`, `/register`) yopiq.
2. **Huquqshunos tasdig'i:** shaxsiy ma'lumotlar Germaniyadagi serverda saqlanadi. Bizning
   xulosamizni (OʻRQ-1125, 27¹-modda faqat biometrik, genetik va telekom ma'lumotlarini
   mahalliylashtiradi, biz 15-moddadagi rozilikka tayanamiz) huquqshunos ko'rib chiqadi. Bu
   foydalanuvchining ishi, biz unga qisqa savol matnini tayyorlaymiz.
3. **Bosh sahifa:** qamrov ("≈22 ming amaldagi hujjat"), bazadagi oxirgi yangilanish sanasi,
   Claude, ChatGPT va Claude Code'ga qanday ulanish, "bu yuridik maslahat emas" degan ogohlantirish.
4. **Limitlar** o'zgarmaydi (kuniga 30 ta qidiruv, 200 ta boshqa chaqiruv, daqiqasiga 10 ta).
   Ochilgandan keyingi birinchi hafta ertalabki hisobotda yangi foydalanuvchilar va limitga
   yetganlar soni kuzatiladi.
5. **E'lon:** qayerda e'lon qilish (Telegram kanallari, LinkedIn, GitHub README) —
   foydalanuvchi hal qiladi.

## Tayyor bo'lish mezonlari

- Har bir qamrov toifasidagi hujjatlar soni lex.uz statistikasidan 2% dan ko'p farq qilmaydi.
- Amaldagi hujjatlarning ≥99% i parse qilingan va indekslangan. Qolganlari ro'yxatda sababi
  bilan turadi (`pdf_only`, xato).
- Kodekslar bo'yicha savollarda R@10 ≥ 0,85, yangi savollarda o'lchangan va yozilgan.
  `search_law` p95 ≤ 1 s.
- Tungi `update` to'liq bazada xatosiz ishlaydi va yangi qamrovdagi hujjatni qo'shadi.
- Zaxira nusxa yangi hajmda ishlaydi va bir marta tiklab ko'rilgan.
- `robots.txt` va bosh sahifa tayyor, huquqshunos javob bergan.

## Modullar va fayllar

```
src/qonunshunos/crawler/listing.py   toifa/yil bo'yicha ro'yxatlar, davom ettirish
src/qonunshunos/crawler/full.py      to'liq crawl: navbat, pauza, xatolarda kutish, holat
src/qonunshunos/crawler/sample.py    sinov to'plami va parser hisoboti
src/qonunshunos/crawler/update.py    SCOPE_KINDS → qamrov qoidasi, navbat ustuvorligi
src/qonunshunos/index/writer.py      rekvizitlar rejimi, HNSW'ni o'chirib/qurib yozish
src/qonunshunos/site.py              robots.txt, bosh sahifa matni
deploy/backup.sh                     saqlash muddatlari, kichik auth dump
deploy/home/backup-pull.sh           home'dagi saqlash muddati (30 → 14 kun)
eval/questions.yaml                  ≈30 ta yangi savol
```

## Ishlar tartibi

1. ✅ Qamrov filtri bo'yicha tadqiqot: toifa filtri o'rniga `/uz/search/nat` bo'limi
   (`docs/research/lexuz.md`, 9-bo'lim).
2. ✅ Ro'yxatlar `minor`/yil bo'yicha (`qonunshunos scope`): 15 811 ta, lex.uz soni bilan aynan mos.
3. ⏭ Sinov to'plami alohida qilinmadi: xom sahifalar saqlanadi, parser keyin tuzatilib, qayta
   yuklamasdan qayta parse qilinadi. Parser ogohlantirishlari to'liq yuklashdan keyin ko'riladi.
4. ⏳ To'liq yuklab olish (`qonunshunos crawl-full`) `myserver`da, 2026-11-07 22:25 dan (Toshkent).
5. Zaxira nusxa muddatlarini o'zgartirish (serverda o'zgarish: avval foydalanuvchidan so'raladi).
6. Indekslash: HNSW'siz yozish → indeksni qurish → rekvizitlar. `minor=Y` bo'yicha qaror
   qabul qilindi (pastda, "O'zgartirish kirituvchi hujjatlar").
7. Baholash: yangi savollar, R@10 va javob vaqti, kerak bo'lsa hujjat turi og'irligi.
8. Tungi `update`ni kengaytirish (musbat ID'li lotin hujjatlar ham), bir kecha kuzatish.
9. `robots.txt`, bosh sahifa, huquqshunosga savol → ochish.

## Bajarilganlar va dizayndan farqlar (2026-11-08)

- **Qamrov — `/uz/search/nat`.** lex.uz qidiruvida milliy qonunchilik alohida bo'lim: unda
  Konstitutsiya, kodekslar, qonunlar, Prezident va hukumat hujjatlari, vazirlik va idoralar
  buyruqlari bor. Mahalliy hokimiyat (`loc`), xalqaro (`int`), texnik (`tech`), sud (`court`)
  va Oliy Majlis kengashlari (`oliy`) hujjatlari boshqa bo'limlarda. Filtrlar: `lang=4` (lotin),
  `status=Y|R|N`, `minor=N|Y`, `form_id`, `fyear`.
- **Hajm taxmindan kichik:** amaldagi lotin hujjatlar **15 811** ta (≈22 ming emas): 10 405 ta
  yaxlit (`minor=N`) va 5 406 ta faqat o'zgartirish kirituvchi (`minor=Y`). Kuchini yo'qotganlar
  12 700 ta. So'rovlar ≈31 600 ta, ya'ni ≈18 soat.
- **Ro'yxatlar yil bo'yicha** (`data/listings/scope/{N|Y}-{yil}.json`, 1920–2026). 16 ta hujjat
  1990-yildan oldingi (eng eskisi 1961). Har bir faylda lex.uz ko'rsatgan son (`expected`) bilan
  solishtirildi: hammasi mos.
- **Joy — `myserver`.** `home` ishxonadagi kompyuter va uning IP'si butun ishxona uchun umumiy,
  shuning uchun yuklab olish serverdan ishlaydi (foydalanuvchi qarori, 2026-11-07). Embedding
  keyin `home`da yoki serverda qilinadi.
- **Ishga tushirish:** `systemd-run --user --unit=qonunshunos-crawl-full … qonunshunos crawl-full`
  (log: `journalctl --user -u qonunshunos-crawl-full`, holat: `data/crawl-full.json`).
  20 ta hujjatlik sinov (`--limit 20`) xatosiz o'tdi.
- **Musbat ID'li lotin hujjatlar:** 402 ta (asosan Markaziy bank va vazirliklar buyruqlari).
  Kartochkasida til "Узбекский (Л)". `resolve.py` tuzatildi, tungi `update` hali faqat manfiy
  ID'li yangi hujjatlarni qamrovga oladi.
- **Tungi yangilash bilan pauza.** Birinchi kecha crawler pauza qilmadi: `oneshot` xizmat ishlab
  turganda holati `activating`, `systemctl is-active` esa faqat `active`ni tan oladi. Ustma-ust
  tushgani 4 ta so'rov. Tuzatildi (`ActiveState` o'qiladi), keyingi deploy bilan ishga tushadi.
- **Oraliq natija (2026-11-08 09:30 UTC):** 13 856 ta hujjat saqlandi, 0 xato, 1 tasi topilmadi,
  parser 4 450 ta ogohlantirish berdi (ko'rib chiqiladi). `data/raw` 537 MB, `data/parsed` 848 MB.
- **Yuklab olish tugadi (2026-11-08 11:47 UTC, 18 soat 22 daqiqa):** 15 811 tadan 15 810 tasi
  saqlandi, 0 xato. Topilmagani bitta: `-4648958` (VM qarori, 17.12.2019, 1009-son), ro'yxatda
  bor, lekin sahifasi lex.uz'da 404 (qayta urinildi). Tungi pauza ishlamagani uchun
  ustma-ust tushgan so'rovlar 4 ta.
- **Parser ogohlantirishlari (14 045 hujjatdan 4 414 tasida).** Deyarli hammasi parser
  tanimagan blok turlari: `DEPARTMENTAL` (Adliya vazirligida ro'yxatdan o'tkazilgani, 3 267),
  `UNOFFIAL` ("Norasmiy tarjima", 576), `EXTRACT` ("[Ko'chirma]", 427), `COMMENT_FOR_WARNING`
  ("Hujjat matni rus tilida berilgan", 199), `APPL_BANNER_PORTRAIT_*` (ilova sarlavhalari),
  `TEXT_BOLD`, `TEXT_ITALIC`, `TEXT_SUD`, `TEXT_15_LEFT` (oddiy matn), `signCont`
  (tasdiqlash muhrlari). Ilova sarlavhalari va matn bloklari tashlab yuborilayotgan edi.
  Tuzatildi: belgilar `notes`ga, ilova bannerlari sarlavhaga, qolganlari matnga; "27-1-modda"
  ham tanildi. Ogohlantirishli 400 ta tasodifiy hujjat qayta parse qilindi: ogohlantirish 0.
  `PARSER_VERSION` = 2, hamma hujjat indekslashdan oldin xom sahifadan qayta parse qilinadi.
- **O'zgartirish kirituvchi hujjatlar (foydalanuvchi qarori, 2026-11-08): aralash.** 5 406 ta
  `minor=Y` hujjatdan 5 357 tasining nomi "…ga o'zgartish (qo'shimcha) kiritish to'g'risida",
  "…kuchini yo'qotgan deb topish", "…munosabati bilan" kabi. Ularning o'zgartirishlari asosiy
  hujjatlarning amaldagi tahririda bor, to'liq indekslansa qidiruvda bir qoida ikki marta
  chiqadi. Shuning uchun ulardan faqat rekvizitlar olinadi (`content = 'requisites'`,
  `find_document` topadi, `get_*` buni tushuntiradi). Qolgan 49 tasi (masalan, "Suv kodeksini
  tasdiqlash to'g'risida", uchuvchisiz apparatlar tartibi) to'liq indekslanadi. Qoida:
  `crawler/full.py`dagi `AMENDING_TITLE_RE`, `index` buyrug'i uni qamrov ro'yxatidan oladi.
- **Tungi `update`dagi yangi hujjatlar endi RSS'dan emas, qamrov ro'yxatidan.** Turi va organi
  bo'yicha qamrovni aniqlash ishonchsiz (hokim farmoyishi ham "farmoyish"). Shuning uchun har
  kecha `/uz/search/nat` ro'yxatlarining (`minor=N` va `minor=Y`, eng yangisi birinchi)
  dastlabki 3 sahifasi o'qiladi (≈6 so'rov), bizda yo'q amaldagi hujjatlar qo'shiladi,
  o'zgartirish kirituvchilari faqat rekvizitlar bilan. Lotin tarjimasi hujjatdan bir necha
  hafta keyin chiqishi mumkin, shuning uchun bitta sahifa emas, uchtasi. Musbat ID'li lotin
  hujjatlar ham shu yo'l bilan keladi. `SCOPE_KINDS` olib tashlandi; RSS faqat havola
  qilingan hujjatlarni qayta tekshirish uchun qoldi.

## Xavflar

- **lex.uz bizni bloklashi mumkin.** 25 soat davomida to'xtovsiz so'rov — oddiy foydalanuvchidan
  ko'p. Tezlikni oshirmaymiz, xatolar ko'paysa to'xtaymiz. Bloklansa, tunda kamroq
  tezlikda davom etamiz va "Adolat" markaziga xatni oldinroq yuborishni ko'rib chiqamiz.
- **Parser kutilmagan tuzilmalarga duch keladi.** Shuning uchun avval sinov to'plami. Xom
  sahifalar saqlanadi, parser tuzatilsa, qayta yuklamasdan qayta parse qilinadi.
- **Server RAM'i yetmay qolishi mumkin.** HNSW (≈0,6 GB) va PostgreSQL boshqa ilovalar bilan
  birga 3,7 GB'ga sig'ishi kerak. Indeks qurilgandan keyin bo'sh RAM va qidiruv vaqti o'lchanadi.
  Yetmasa, server tarifini oshirish kerak bo'ladi (foydalanuvchi hal qiladi).
- **Qidiruv sifati tushadi.** Bu "Qidiruv sifati" bo'limida o'lchanadi va tuzatiladi.
- **Tunnel uzilishi.** Indekslash 100 talik tranzaksiyalar bilan ishlaydi va davom ettirsa bo'ladi.
  Uzilsa, faqat oxirgi to'plam qayta yoziladi.
