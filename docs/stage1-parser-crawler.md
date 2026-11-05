# 1-bosqich: parser va crawler

Holat (2026-11-05): ✅ bajarildi. Tadqiqot: [lexuz.md, 8-bo'lim](research/lexuz.md).
Tegishli hujjatlar: [PLAN.md](../PLAN.md), [lex.uz tadqiqoti](research/lexuz.md).

## Maqsad

lex.uz'dagi lotin hujjat sahifasini (`/docs/-{id}`) va rekvizitlar kartochkasini yuklab olish,
ularni xom holda diskda saqlash va 2-bosqich (indekslash) uchun tuzilgan JSON'ga aylantirish.
Avval namunaviy to'plamda ishlanadi: Konstitutsiya va barcha amaldagi kodekslar (lotin, 21 ta
hujjat: 20 ta kodeks + Konstitutsiya).

## Tayyor bo'lish mezonlari

- `qonunshunos fetch <id>` hujjat va kartochkasini `data/raw/`ga yuklab oladi.
- `qonunshunos parse <id>` `data/parsed/<id>.json`ni yaratadi.
- `qonunshunos crawl-sample` namunaviy to'plamni yuklab oladi, parse qiladi va hisobot chiqaradi:
  har bir hujjat uchun moddalar soni va parser ogohlantirishlari.
- Mehnat kodeksida barcha moddalar (2026-11-05 holatiga 593 ta) topiladi va ularning bob/bo'lim
  yo'li to'g'ri chiqadi.
- `uv run pytest` va `uv run ruff check .` o'tadi. Testlar tarmoqqa chiqmaydi.

## Ishlar tartibi

1. ✅ **Qolgan tadqiqot** — [lexuz.md, 8-bo'lim](research/lexuz.md): qaror va farmonlar
   tuzilishi, ilovalar, jadvallar, faqat PDF'li yangi hujjatlar, card1, kodekslar ro'yxati
   (`fform_id=3964`) va postback bilan sahifalash.
2. ✅ **Loyiha karkasi:** `pyproject.toml` (uv), `src/qonunshunos/`, `tests/`, ruff, `.gitignore`
   (`data/`), qisqa README.
3. ✅ `text/normalize.py` + testlar.
4. ✅ `parser/document.py` + fixture'lar + testlar.
5. ✅ `parser/card.py` + testlar.
6. ✅ `crawler/` (klient, saqlash, ro'yxatlar) + CLI + testlar.
7. ✅ Namunaviy to'plamni yuklab olish, natijalarni tekshirish, parserni tuzatish.

## Natija (2026-11-05)

`qonunshunos crawl-sample`: 21 ta hujjat (Konstitutsiya + 20 ta amaldagi kodeks), ≈44 ta so'rov,
xatosiz. Parserda ogohlantirish yo'q, takroriy yoki bo'sh modda yo'q.

| Hujjat | Moddalar | Hujjat | Moddalar |
|---|---:|---|---:|
| Konstitutsiya | 155 | Mehnat | 593 |
| Fuqarolik (1-qism) | 386 | Fuqarolik (2-qism) | 811 |
| Jinoyat | 406 | Jinoyat-protsessual | 773 |
| Maʼmuriy javobgarlik | 673 | Fuqarolik protsessual | 513 |
| Soliq | 500 | Bojxona | 419 |
| Iqtisodiy protsessual | 390 | Maʼmuriy sud ishlari | 309 |
| Oila | 220 | Jinoyat-ijroiya | 200 |
| Budjet | 179 | Suv | 165 |
| Uy-joy | 141 | Havo | 136 |
| Saylov | 116 | Yer | 110 |
| Shaharsozlik | 85 | | |

Sinov paytida topilib tuzatilganlar: `599- modda` / `184³ -modda` (defis atrofida bo'shliq),
bo'sh `CLAUSE_DEFAULT`, `TABLE_STD`, `OFFICIAL_SOUR_TEXT` (rasmiy manba PDF havolasi), modda
ichidagi kichik sarlavhalar (Suv kodeksi, jadval ustida).

Ochiq qolganlar (2-bosqichda yoki to'liq yuklashda ko'riladi):

- Faqat PDF'li hujjatlar (`content="pdf_only"`): HTML qachon paydo bo'lishini kuzatish.
- Farmon va qarorlar faqat 4 ta namunada tekshirildi; to'liq yuklashda ogohlantirishlar
  hisobotiga qarab parser kengaytiriladi.
- Katta jadvallar (masalan VM 916-son) bo'laklashda alohida chegaralanadi.

## Texnologiyalar

Python ≥3.12, uv, httpx, beautifulsoup4 + lxml, pydantic v2, pytest, ruff. CLI uchun argparse.

## Modullar

```
src/qonunshunos/
  text/normalize.py      apostroflar, bo'shliqlar, <sup> → ¹²³
  parser/models.py       pydantic modellar (quyida)
  parser/document.py     hujjat HTML → ParsedDocument
  parser/card.py         card1 HTML → DocumentCard
  crawler/client.py      ehtiyotkor HTTP klient
  crawler/store.py       data/raw'ga saqlash
  crawler/listing.py     qidiruv ro'yxatlari (ASP.NET postback)
  crawler/sample.py      namunaviy to'plam
  cli.py                 `qonunshunos` buyrug'i
```

## Natija modeli (pydantic, soddalashtirilgan)

```python
class Link:       doc_id: int; elem_id: int | None; ondate: str | None; text: str
class Paragraph:  elem_id: int; text: str; links: list[Link]
class Change:     elem_id: int; text: str; links: list[Link]     # CHANGES_ORIGINS
class Heading:    elem_id: int; level: int; kind: str; number: str | None; title: str; text: str

class Unit:
    kind: str                  # "modda" | "band" | "kirish" | "matn"
    number: str | None         # ko'rinishi: "161", "126¹"
    title: str | None
    elem_id: int | None
    path: list[str]            # ["UMUMIY QISM", "I BOʻLIM. UMUMIY QOIDALAR", "1-bob. Asosiy qoidalar"]
    paragraphs: list[Paragraph]
    changes: list[Change]
    okoz: list[str]
    comments: list[Comment]    # "LexUZ sharhi"lar ("Oldingi tahrirga qarang"siz), havolalari bilan

class Table:      elem_id: int; rows: list[list[str]]

class Unit:  # qo'shimcha: kind "band" | "ilova_matn" ham; tables: list[Table]; appendix: str | None

class ParsedDocument:
    lex_id: int                # lotin sahifa ID'si (manfiy)
    content: str               # "html" | "pdf_only" (8.1-bo'lim)
    signature: str | None      # SIGNATURE
    place: str | None; signed_date: str | None; signed_number: str | None  # ACT_ESSENTIAL_ELEMENTS*
    lang: str                  # "uz-Latn"
    url: str
    title: str                 # <title>dan
    number: str | None         # "OʻRQ-42"
    date: str | None           # ISO sana
    edition_date: str | None   # joriy tahrir sanasi (#dd3)
    alternates: dict[str, int] # {"uz-Cyrl": 6445145, "ru": 6445147, "en": 6451070}
    okoz: list[str]
    publication_origin: str | None
    headings: list[Heading]
    units: list[Unit]
    warnings: list[str]
    parser_version: str

class DocumentCard:            # /actinfo/card1
    title, doc_type, form, bodies (organ, imzolagan shaxs, sana, raqam, joy),
    registration_number, registration_date, language,
    status ("in_force" | "lost_force" | "not_in_force" | "unknown"), status_raw,
    entry_into_force, validity, lost_force_at, lost_force_reason, normativity
```

Kartochka qiymatlari URL'ga qarab lotin, kirill yoki rus tilida keladi ("Amalda", "Действующий"
va h.k.). Holat va boshqa ro'yxat qiymatlari uchun barcha variantlar bitta kanonik qiymatga
xaritalanadi. Sanalar `dd.mm.yyyy` → ISO.

## Parser qoidalari

1. `#divCont` bolalari tartib bo'yicha bir marta o'qiladi.
2. `lx_elem` blokida matn faqat ichki `div[id]`dan olinadi, `lx_elem2` (interfeys tugmalari)
   tashlanadi. Element ID — shu `div`ning `id`si.
3. Class bo'yicha amallar:

   | Class | Amal |
   |---|---|
   | `ACT_TITLE` | zaxira nom (asosiy nom `<title>`dan olinadi) |
   | `TEXT_HEADER_DEFAULT`, `TEXT_BOLD_CENTER` | sarlavha; bo'sh bo'lsa o'tkazib yuboriladi |
   | `CLAUSE_DEFAULT` | yangi `Unit(kind="modda")` |
   | `ACT_TEXT` | joriy unitga paragraf; unit hali bo'lmasa `kind="kirish"` (preambula) |
   | `INDEXES_ON_REF` | `onLBC-{lex_id}` / `onLS-{lex_id}` — hujjat `okoz` / `tsz`iga; qolganlari keyingi kontent oladigan unitga (ID `onLBC-{elem}` keyingi elementni ko'rsatadi) |
   | `CHANGES_ORIGINS` | joriy unitning `changes`iga; unit bo'lmasa (masalan imzodan keyin) hujjatning `changes`iga |
   | `COMMENT` | "Oldingi tahrirga qarang" (`id="edi-…"`) tashlanadi, qolgani joriy unitning (yoki hujjatning) `comments`iga |
   | `TEXT_CENTER lx_no_select` | tahririyat izohi → hujjatning `notes`iga |
   | `PUBLICATION_ORIGIN` | hujjatning `publication_origin`iga |
   | `ACCEPTING_BODY` | hujjat darajasidagi ma'lumot (organ) |
   | `SIGNATURE`, `ACT_ESSENTIAL_ELEMENTS`, `ACT_ESSENTIAL_ELEMENTS_NUM` | hujjatning `signature`, `place`, `signed_date`, `signed_number` maydonlari |
   | `APPL_BANNER_LANDSCAPE_TITLE` | yangi ilova: sarlavhalar stack'i tozalanadi, 1-darajali sarlavha "4-ILOVA" |
   | `ACT_TITLE_APPL` + keyingi `ACT_FORM` | ilova nomi ("… toʻgʻrisida NIZOM"), 1-darajali sarlavha matniga qo'shiladi |
   | `TABLE_STD2`, jadvalli `BY_DEFAULT` | `Table` (qatorlar × kataklar) joriy unitga; unit bo'lmasa ilova uchun `ilova_matn` unit |
   | `FOOTNOTE` | joriy unitga paragraf |
   | `TEXT_CENTER` | sarlavha (5-daraja) |
   | `ACT_FORM` (ilovadan tashqari), bo'sh `BY_DEFAULT`, `NEW_EDITION` | o'tkazib yuboriladi |
   | boshqa class | `warnings`ga yoziladi |

4. Sarlavha darajasi:
   - `UMUMIY QISM`, `MAXSUS QISM` va boshqa `… QISM` → 1 (qism)
   - `I BOʻLIM.`, `BIRINCHI BOʻLIM.` → 2 (bo'lim)
   - `1-bob.`, `I bob.` → 3 (bob)
   - `1-§.`, `… paragraf` → 4 (paragraf)
   - boshqasi → 5

   Yangi sarlavha kelganda stack'dan o'zidan past yoki teng darajadagi sarlavhalar olib tashlanadi.
   Unitning `path`i shu stack'dan olinadi.
5. Modda sarlavhasi: `^(\d+)(<sup>(\d+)</sup>)?-modda\.?\s*(.*)$` → `number="126¹"`, `title`.
   Sarlavhasiz moddalar ham bor, masalan Konstitutsiyada: "1-modda.".
6. Moddasiz hujjatlarda (qaror, farmon, nizom) `^\d+(<sup>\d+</sup>)?\.\s` bilan boshlanadigan
   `ACT_TEXT` yangi `Unit(kind="band")` ochadi. "a)", "b)" kichik bandlar va oddiy xatboshilar shu
   bandga qo'shiladi. Hujjatda `CLAUSE_DEFAULT` bo'lsa, band qoidasi o'chiriladi (kodekslarda "1."
   modda ichidagi qism raqami). Band OKOZ kodi band matnidan oldin keladi, shuning uchun
   `INDEXES_ON_REF` keyingi unitga biriktiriladi (kodekslarda ham shu qoida ishlaydi).
   Sarlavha, imzo va ilova banneri joriy unitni yopadi: keyingi raqamsiz matn yangi `matn` unit
   bo'ladi (birinchi sarlavhadan oldin — `kirish`).
   Ba'zi sahifalarda (masalan Mehnat kodeksi) tahrirlar ro'yxati bo'sh, shuning uchun
   `last_change_date` — `CHANGES_ORIGINS` havolalaridagi eng so'nggi `ONDATE` — ham saqlanadi.
7. Matnni tozalash: `<sup>N</sup>` yuqori indeksga aylanadi, bo'shliqlar bitta probelga
   keltiriladi, apostroflar kanonik shaklga o'tkaziladi: `o`/`g`dan keyin `ʻ` (U+02BB), boshqa
   harfdan keyin `ʼ` (U+02BC). So'z boshidagi qo'shtirnoq o'zgartirilmaydi.
8. Havolalar: `/docs/{id}[?ONDATE=dd.mm.yyyy …]#{elem}` → `Link`.

## Crawler

- **Klient:** httpx, `User-Agent: QonunshunosBot/0.1` (shaxsiy email qo'yilmaydi). So'rovlar
  orasida kamida 2 soniya, parallel so'rov yo'q. Timeout 60 s (Mehnat kodeksi sahifasi 3,5 MB).
  5xx va timeout bo'lsa 3 marta qayta urinadi (2, 4, 8 s). `/Pages/404.aspx`ga yo'naltirish
  `NotFound` deb qaraladi.
- **Saqlash:** `data/raw/docs/{id}.html.gz`, `data/raw/cards/{id}.html.gz` va har birining
  yonida `.meta.json` (url, fetched_at, sha256, HTTP status). `--force` berilmasa qayta
  yuklanmaydi. `data/` git'ga qo'shilmaydi.
- **Ro'yxatlar:** `/uz/search/nat?lang=4&fform_id=…[&fyear=…]`, sahifada 20 ta natija. Keyingi
  sahifa: `#Form1` dagi `__VIEWSTATE`, `__VIEWSTATEGENERATOR` va
  `__EVENTTARGET=ucFoundActsControl$LinkButton1` bilan shu URL'ga POST. "Keyingisi" havolasi
  bo'lmasa yoki natijalar soni ("N hujjat topildi") yig'ilsa to'xtaydi.
- **Faqat PDF'li hujjat** (`#divCont` yo'q, `#pdfBody` bor): `content="pdf_only"` bilan saqlanadi
  va keyingi yangilashda qayta tekshiriladi.
- **Kartochka:** `/actinfo/card1/-{id}` (yorliqlar kirill, qiymatlar rus).
- **Namunaviy to'plam** kodekslar ro'yxatidan (`fform_id=3964`, faqat `status_code_y`) va
  Konstitutsiyadan (`-6445145`) olinadi.

## Testlar

- `tests/fixtures/lexuz/`da haqiqiy sahifalarning qisqartirilgan nusxalari bo'ladi (har biri
  100 KB dan kichik): Konstitutsiya (boshi), Mehnat kodeksi (1–5 va 161-moddalar, o'zgartirish
  manbasi, `5¹)` bandi), PF-60 (moddasiz farmon), VM 897-son qaror (ilovalar, nizom, jadval),
  faqat PDF'li sahifa, card1 (amalda va kuchini yo'qotgan), ro'yxat sahifasi. Qisqartirish uchun
  `scripts/make_fixture.py`.
- Nimalar tekshiriladi:
  - normalizatsiya;
  - hujjat parseri: moddalar soni, sarlavhalar va yo'llar, `5¹)` band, o'zgartirish manbasi va
    uning havolasi, OKOZ, sharhlarning ajratilishi;
  - card parseri: holatni xaritalash, sanalar;
  - klient (`httpx.MockTransport` bilan): 404, qayta urinish, pauza;
  - ro'yxatlar: yashirin maydonlar, natija qatorlari.
