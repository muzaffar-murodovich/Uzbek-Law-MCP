# lex.uz tadqiqoti (0-bosqich)

Sana: 2026-yil 5-noyabr. lex.uz'ga ~25 ta so'rov yuborildi (orasida 1,5–2 soniya pauza bilan).
Quyidagilar sahifalarni kuzatish natijasi, rasmiy hujjatlashtirilgan API emas. Sayt tuzilishi
oldindan ogohlantirmasdan o'zgarishi mumkin.

## 1. Umumiy

- Sayt: ASP.NET WebForms, Microsoft IIS 10.
- `robots.txt` va `sitemap.xml` yo'q (ikkalasi ham `/Pages/404.aspx`ga yo'naltiriladi).
- `/uz/`, `/ru/`, `/en/` prefikslari faqat **interfeys** tilini o'zgartiradi, hujjat matnini emas.
- lex.uz'ning o'z AI platformasi bor: **ai.lex.uz** ("LexAI" platformasi). Bu raqobatchi bo'lishi
  ham, hamkor bo'lishi ham mumkin.

## 2. Hujjat URL'lari

| Nima | URL | Misol |
|---|---|---|
| Asl matn (odatda o'zbek kirill) | `/docs/{id}` | `/docs/6445145` (Konstitutsiya) |
| **O'zbek lotin** | `/docs/-{id}` (manfiy ID) | `/docs/-6445145`, `/uz/docs/-6257288` (Mehnat kodeksi) |
| Rus / ingliz | alohida ID, hujjat sahifasidagi til tugmalarida | Konstitutsiya: rus `6445147`, ingliz `6451070` |
| Muayyan sanadagi tahrir | `/docs/{id}?ONDATE=dd.mm.yyyy` | `?ONDATE=01.05.2023` |
| Tahrirlarni solishtirish | `/docs/{id}?ONDATE2=dd.mm.yyyy&action=compare` | |
| Word | `/docs/{id}?type=doc` | |
| PDF | `/pdfs/{id}` | |
| Hujjat elementiga havola | `/docs/{id}#{element_id}` | `/docs/-1022944#-1023047` (8-modda) |

## 3. Rekvizitlar (metama'lumotlar)

| Endpoint | Mazmuni |
|---|---|
| `/actinfo/card1/{id}` | Yuridik tahlil kartochkasi: nomi, turi, shakli, qabul qilgan organ, qabul qilingan sana, raqami, tili, **holati** (Amalda / kuchini yo'qotgan), kuchga kirish sanasi, amal qilish muddati, kuchini yo'qotgan sana va sababi |
| `/actinfo/card2/{id}` | Qonunchilik tarmoqlari umumhuquqiy klassifikatori (OKOZ) kodlari: hujjatga va uning elementlariga |
| `/actinfo/basrev/{id}`, `/actinfo/revhis/{id}` | Qayta ko'rib chiqilgan hujjatlar va qayta ko'rib chiqishga asos bo'lgan hujjatlar |
| `/actinfo/correspondents/{id}`, `/actinfo/respondents/{id}` | Hujjatlar orasidagi bog'lanishlar |
| `/uz/doc-passport/-{id}` | Qo'shimcha ma'lumotlar |

Eslatma: kartochkadagi qiymatlar tili g'alati: kirill hujjatda lotincha ("Amalda"), lotin hujjatda
ruscha ("Действующий"). Parser ikkala variantni ham tanishi kerak.

## 4. Hujjat matnining HTML tuzilishi

Har bir hujjat elementi alohida blok:

```html
<div class="CLAUSE_DEFAULT lx_elem">
  <div class="lx_elem2"><div class="lx_elem3">…interfeys tugmalari…</div></div>
  <div id="-6257549">1-modda. Ushbu Kodeks bilan tartibga solinadigan munosabatlar</div>
</div>
```

(Mehnat kodeksi, lotin: `https://lex.uz/docs/-6257288#-6257549`.)

Matn faqat ichki `div[id]`dan olinadi. `lx_elem2/lx_elem3` ichidagi tugmalar ("Ҳужжатга таклиф
юбориш", "Аудиони тинглаш" …) olib tashlanadi.

| Class | Mazmuni | Biz uchun |
|---|---|---|
| `ACT_TITLE` | Hujjat nomi | sarlavha |
| `ACT_FORM` | Hujjat shakli | — |
| `TEXT_HEADER_DEFAULT` | Qism / bo'lim / bob ("I BOʻLIM. UMUMIY QOIDALAR", "1-bob. …") | ierarxiya |
| `CLAUSE_DEFAULT` | Modda sarlavhasi ("1-modda. …") | **asosiy birlik** |
| `ACT_TEXT` | Xatboshi / qism / band matni | modda matni |
| `TEXT_BOLD_CENTER` | Markazlashtirilgan sarlavha ("MUQADDIMA") | ierarxiya |
| `BY_DEFAULT`, `NEW_EDITION` | Bo'sh / xizmat bloklari | o'tkazib yuboriladi |
| `CHANGES_ORIGINS` | O'zgartirish manbasi: "(4-moddaning ikkinchi qismi … OʻRQ-963-sonli Qonuni tahririda — …)" | modda metama'lumoti ("oxirgi o'zgartirish") |
| `INDEXES_ON_REF` | Moddaning klassifikator kodlari: "[ OKOZ: … ]", "[ TSZ: … ]" | mavzu bo'yicha filtr / boost |
| `COMMENT`, `COMMENTLEXUZ` | "Oldingi tahrirga qarang", "LexUZ sharhi. Qarang: …" | normativ matnga qo'shilmaydi, havolalar alohida saqlanadi |

- Matn ichidagi havolalar `/docs/{id}#{element_id}` ko'rinishida, ya'ni hujjatlar va moddalar
  orasidagi bog'lanish grafini qurish mumkin.
- Lotin versiyasida element ID'lari ham manfiy. Shuning uchun javobda aniq moddaga havola beriladi.
- Hajm: Konstitutsiya ~0,75 MB HTML / ~100 ming belgi; Mehnat kodeksi ~3,5 MB HTML /
  ~715 ming belgi, 593 modda, 95 sarlavha.

### O'zbekcha apostroflar

Lotin matnlarda rasmiy imlo ishlatilgan: `ʻ` (U+02BB, oʻ / gʻ) va `ʼ` (U+02BC, tutuq belgisi).
Foydalanuvchilar esa `o'`, `o‘`, `o’`, `` o` `` deb yozadi. Indekslash va qidiruvda hammasi bitta
shaklga keltiriladi.

### Parser uchun tafsilotlar

- Hujjat matni `div#divCont` ichida. Uning bolalari tekis ketma-ketlikda keladi, ichma-ich
  daraxt yo'q. Mehnat kodeksida bunday bolalar 5 286 ta.
- Ketma-ketlik namunasi (Mehnat kodeksi):

  ```
  INDEXES_ON_REF       hujjat darajasidagi OKOZ/TSZ kodlari (ACT_FORM'dan oldin)
  ACT_FORM, ACT_TITLE, NEW_EDITION, BY_DEFAULT
  TEXT_HEADER_DEFAULT  "UMUMIY QISM" → "I BOʻLIM. UMUMIY QOIDALAR" → (bo'sh) → "1-bob. Asosiy qoidalar"
  CLAUSE_DEFAULT       "1-modda. …"
  INDEXES_ON_REF       moddaning OKOZ kodlari (modda sarlavhasidan keyin)
  ACT_TEXT …           modda matni (har bir qism yoki band alohida blok)
  COMMENT              "Oldingi tahrirga qarang." (o'zgartirilgan xatboshidan oldin)
  CHANGES_ORIGINS      o'zgartirish manbasi (o'zgartirilgan xatboshidan keyin)
  …
  PUBLICATION_ORIGIN   rasmiy nashr manbalari ro'yxati (eng oxirida)
  ```

- Bo'sh `TEXT_HEADER_DEFAULT` bloklari uchraydi, ular o'tkazib yuboriladi.
- `CHANGES_ORIGINS` ichida o'zgartirish kiritgan hujjatga havola bor:
  `<a href="/docs/-7108715?ONDATE=21.09.2024 00#-7108833">Qonuni </a>`. Matn namunasi:
  "(4-moddaning ikkinchi qismi Oʻzbekiston Respublikasining 2024-yil 20-sentabrdagi OʻRQ-963-sonli
  Qonuni tahririda — Qonunchilik maʼlumotlari milliy bazasi, 21.09.2024-y., 03/24/963/0735-son)".
  Ba'zan kelajakdagi kuchga kirish sanasi ham yoziladi: "Kuchga kirish sanasi — 2026-yil 12-sentabr".
- `COMMENT` ikki xil bo'ladi: "Oldingi tahrirga qarang." (navigatsiya, kerak emas) va
  "LexUZ sharhi. Qarang: …" (boshqa hujjatlarga havolalar bilan).
- Kiritilgan modda va bandlar `<sup>` bilan yoziladi: `5<sup>1</sup>) …` (band),
  `39<sup>1</sup>-moddalari`, `97 — 103<sup>1</sup>-moddalari`. Matnda ular Unicode yuqori
  indeksga (¹²³…) aylantiriladi.
- `<title>` formati: `&nbsp;O‘RQ-42-сон 20.07.2006.&nbsp;Mualliflik huquqi va turdosh huquqlar
  toʻgʻrisida`, ya'ni raqam (lotin sahifada ham kirillcha "-сон" bilan), sana va nom. Raqami yo'q
  hujjatda faqat sana va nom bo'ladi: `&nbsp; 30.04.2023.&nbsp;Oʻzbekiston Respublikasi
  Konstitutsiyasi`. `ACT_TITLE` ko'pincha katta harflarda yozilgan, shuning uchun nomni `<title>`dan
  olish ma'qul.
- Tahrir sanalari `#dd3` ochiluvchi ro'yxatida: birinchisi (havolasiz) joriy tahrir, qolganlari
  `lxOpenUrl('/docs/{id}?ONDATE=…')`.
- Til tugmalari: `Рус` → `openUrl('/docs/6445147')`, `Eng` → `openUrl('/docs/6451070')`,
  `Ўзб` / `O’zb` → kirill / lotin versiya. Joriy versiya tugmasida `onclick` bo'lmaydi.
- Hujjatlar ichidagi havolalarda uchragan ID'lar (nomi hali tekshirilmagan): `111453` (Jinoyat
  kodeksi bo'lsa kerak), `97664` (Ma'muriy javobgarlik to'g'risidagi kodeks bo'lsa kerak), `111460`.
- Statistika sahifasida ro'yxatlarga havola yo'q, shuning uchun "Kodeks" shaklining `form_id`si
  hali topilmagan. Bosh sahifadagi havolalar: `sort_id=3975&form_id=3968` — "Qonun" shakli
  (1 590 ta lotin hujjat), `sort_id=3985` — Prezident hujjatlari (5 612 ta).

## 5. Hujjatlar ro'yxati va yangilanishlar

- Qidiruv ro'yxatlari: `/uz/search/nat?lang=4&sort_id=…[&form_id=…]`. Sahifada 20 ta natija.
  Sahifalash ASP.NET `__doPostBack` orqali bo'ladi, ya'ni `__VIEWSTATE` bilan POST so'rov kerak.
- `lang` kodlari (kuzatilgan): `1` rus, `2` ingliz, `3` o'zbek kirill, `4` o'zbek lotin.
- Boshqa bo'limlar: `/uz/search/oliy`, `/loc` (mahalliy), `/int` (xalqaro), `/tech`, `/court`.
- Yangi hujjatlar: **RSS** `/uz/rss` (lotin hujjat havolalari bilan) va
  `/uz/search/official?lang=4&pub_date=today|week|month`.
- O'zgartirish kiritgan hujjat matnida o'zgartirilgan hujjatlarga havolalar bo'ladi. Kunlik
  yangilashda shular qayta yuklanadi (tahrir sanasi `ONDATE` ro'yxatidan tekshiriladi).

## 6. Hajm (lex.uz statistikasi, 2026-11-05)

Bazada jami 166 249 hujjat bor (barcha til versiyalari alohida sanalgan).

| Toifa | Jami (barcha tillar) | O'zbek lotin | Amalda (barcha tillar) | Kuchini yo'qotgan |
|---|---:|---:|---:|---:|
| Qonun hujjatlari (Konstitutsiya, kodekslar, qonunlar, OM qarorlari) | 24 865 | 7 989 | 23 126 | 1 576 |
| ↳ shundan kodekslar | 95 | 28 | 71 | 24 |
| ↳ shundan qonunlar | 5 497 | 1 590 | 4 496 | 848 |
| Prezident hujjatlari | 20 382 | 5 612 | 15 759 | 4 623 |
| Hukumat qarorlari | 38 920 | 11 543 | 22 132 | 16 788 |
| Vazirlik va idoralar hujjatlari | 27 810 | 9 280 | 12 464 | 15 334 |
| *MVP qamrovi jami* | | *≈34 400* | | |
| Mahalliy hokimiyat qarorlari | 29 462 | 13 085 | 22 384 | 7 078 |
| Xalqaro hujjatlar | 5 117 | 1 662 | 4 998 | 119 |
| Oliy Majlis kengashlari hujjatlari | 12 936 | 4 319 | 12 576 | 360 |
| Sud amaliyoti | 1 616 | 564 | 1 613 | 3 |
| Sud hujjatlari | 1 084 | 371 | 805 | 279 |
| Texnik hujjatlar | 3 860 | 792 | 3 236 | 624 |

Taxmin: MVP qamrovidagi ≈34 400 ta lotin hujjatning ≈22 mingtasi amalda.

**Resurslarga ta'siri (taxmin):**

- Yuklab olish: ≈22 ming hujjat + kartochkalar ≈ 45 ming so'rov. 2 soniyada 1 so'rov tezligida
  bu 1–1,5 sutka davom etadi, hajmi bir necha GB.
- Bo'laklar: ≈0,5 mln. `multilingual-e5-small` (int8, ONNX) 2 vCPU'da ularni 4–8 soatda
  embedding qiladi, ya'ni boshlang'ich indekslashni Hetzner serverning o'zida bajarish mumkin.
- Vektorlar: `halfvec(384)` bilan ~0,4 GB + HNSW indeksi. 4 GB RAM'ga sig'adi, lekin chegaraga yaqin.

## 7. Huquqiy holat ⚠️

1. **Mualliflik huquqi.** "Mualliflik huquqi va turdosh huquqlar toʻgʻrisida"gi Qonun (OʻRQ-42,
   20.07.2006), [8-modda](https://lex.uz/docs/-1022944#-1023047): *"rasmiy hujjatlar (qonunlar,
   qarorlar, toʻxtamlar va shu kabilar), shuningdek ularning rasmiy tarjimalari"* mualliflik huquqi
   obyekti bo'lmaydi.
2. **lex.uz shartlari.** [Axborotni taqdim etish shartlari](https://lex.uz/uz/axborot)da shunday
   yozilgan:
   - axborot resursi mulk huquqi obyekti bo'lib, unga egalik huquqi "Adolat" markaziga tegishli;
   - *"Ushbu axborot resursidan olgan axborotni faqat shaxsiy maqsadlarda foydalanishingiz mumkin.
     Daromad olish maqsadida maʼlumotlardan nusxa olish, tarqatish, sotish, berish resurs egasining
     yozma roziligisiz taqiqlanadi. Boshqa resurslarda axborotdan foydalanish (normativ huquqiy
     hujjatlarni istisno qilgan xolda) mazkur axborot resursiga havola qilgan xolda yoʻl qoʻyiladi."*
3. **Amaliyot.** Markaz LexUz oflayn dasturini har bir kompyuter uchun alohida litsenziya kaliti
   bilan beradi, ya'ni ma'lumotlarni tijoriy litsenziyalash tajribasi bor.
4. **Xulosa (bu yuridik maslahat emas).** Qonun matnlarining o'zi mualliflik huquqi bilan himoyalanmagan.
   Lekin lex.uz bazasidan pullik xizmat uchun nusxa olish sayt shartlariga zid bo'ladi. Eng xavfsiz
   yo'l — Markazdan yozma rozilik yoki ma'lumot almashish shartnomasini olish
   ([xat loyihasi](../adolat-markazi-xat.md)). Ishga tushirishdan oldin yurist bilan maslahatlashish kerak.
5. **Loyiha qarori (2026-11-05).** Hozircha xizmat bepul, har bir javobda lex.uz'ga havola
   beriladi. Xat pullik tariflar qo'shilganda, ular ishga tushishidan oldin yuboriladi
   ([PLAN.md, 3-bo'lim](../../PLAN.md)).

### Markaz kontaktlari

O'zbekiston Respublikasi Adliya vazirligi qoshidagi "Adolat" milliy huquqiy axborot markazi
davlat muassasasi. Manzil: Toshkent sh., Mirobod tumani, Amir Temur shohko'chasi, 19-uy.
Tel.: (55) 510-47-87. E-mail: info@adolatmarkazi.uz. Sayt: adolatmarkazi.uz.
Telegram: t.me/lexuzofficial.
