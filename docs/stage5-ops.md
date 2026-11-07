# 5-bosqich: zaxira nusxa, monitoring, kunlik yangilash

Holat (2026-11-07): ✅ bajarildi, `myserver` va `home`da ishlayapti (pastda "Natija"). Tegishli hujjatlar:
[PLAN.md](../PLAN.md) (1-, 5- va 8-bo'limlar), [4-bosqich](stage4-auth-limits.md),
[lex.uz tadqiqoti](research/lexuz.md) (5-bo'lim).

## Maqsad

Xizmat `myserver`da ishlayapti. Lekin hozir uni kimdir kuzatib turishi kerak: baza faqat shu
serverda turibdi, server to'xtasa hech kim bilmaydi, lex.uz'da qonun o'zgarsa bizdagi matn
eskirib qoladi. Bu bosqichda:

1. **Zaxira nusxa.** Baza har kecha `pg_dump` bilan saqlanadi. Nusxa `home`ga ham ko'chiriladi,
   chunki server diski yo'qolsa, shu diskdagi nusxa ham yo'qoladi.
2. **Monitoring.** Sayt ishlamay qolsa yoki tungi ish xato bilan tugasa, Telegram'ga xabar keladi.
   Har kuni ertalab qisqa hisobot ham keladi.
3. **Kunlik yangilash.** Har kecha lex.uz'dagi yangi hujjatlar ko'riladi va o'zgargan hujjatlar
   qayta yuklanib, qayta indekslanadi.
4. **Tozalash.** `auth-cleanup` har kecha ishlaydi: eskirgan kodlar, tokenlar va 12 oydan eski
   so'rov matnlari o'chiriladi.

Oddiy qilib aytganda: zaxira nusxa — kalitning nusxasini qo'shnida saqlash. Monitoring —
uyda tutun sezgichi. Kunlik yangilash — gazetani har kuni ertalab varaqlab, kerakli sahifani
kesib olish.

## Hozirgi holat (2026-11-07 da tekshirildi)

- `myserver`: 38 GB diskdan 25 GB bo'sh, 3,8 GB RAM, ≈2,3 GB bo'sh. `qonunshunos` bazasi 104 MB.
- Boshqa ilovalarning zaxirasi `~/backups/pg_backup.sh`da (cron, 03:00 UTC, 14 kun saqlanadi).
  Nusxalar **faqat shu serverda** saqlanadi, tashqariga ko'chirilmaydi.
- `home` `myserver`ga o'z kaliti bilan SSH orqali kira oladi. `home`da 35 GB bo'sh joy bor va
  `systemd --user` timer'lari ishlaydi (`Linger=yes`). `myserver`da Tailscale yo'q.
- Serverda `data/` ichida faqat model bor. Xom sahifalar (`data/raw`, 86 hujjat ≈ 79 MB gzip'dan
  oldin) Mac'da turibdi.
- lex.uz RSS (`/uz/rss`): oxirgi bir oydagi 120 ta yangi hujjat. Har bir yozuvda lotin ID,
  hujjat turi va raqami bor, masalan: "Prezidentining farmoyishi №F-63. Qabul qilingan sana
  06.11.2026". Kuniga o'rtacha 4 ta hujjat chiqadi.

## Tayyor bo'lish mezonlari

- Har kecha `qonunshunos` bazasining dump'i olinadi, 14 kun saqlanadi. `home` uni (va
  `~/backups`dagi boshqa nusxalarni ham) har kecha tortib oladi va 30 kun saqlaydi.
- **Tiklash sinovi:** dump'dan bo'sh bazaga tiklab, `search_law` ishlashi bir marta qo'lda
  tekshiriladi. Qadamlar shu hujjatga yoziladi.
- `home` har 5 daqiqada `https://qonunshunos.muzaffar.zip/healthz`ni tekshiradi. Ketma-ket 2
  marta xato bo'lsa, Telegram'ga xabar ketadi. Sayt tiklanganda yana xabar keladi.
- Tungi ishlarning (yangilash, zaxira, tozalash) har biri xato bilan tugasa, Telegram'ga xabar
  keladi (systemd `OnFailure=`).
- Har kuni ertalab hisobot keladi: kecha nechta hujjat yangilandi, xatolar, foydalanuvchilar va
  chaqiruvlar soni, disk, oxirgi zaxira va `home`ga oxirgi ko'chirish vaqti.
- `qonunshunos update` lex.uz'dan yangi va o'zgargan hujjatlarni topadi va qayta indekslaydi.
  So'rovlar orasida kamida 2 soniya o'tadi va bir kechada so'rovlar soni cheklangan.
- Testlar tarmoqqa chiqmaydi: RSS va sahifalar `tests/fixtures`dan olinadi.

## Kunlik yangilash: qanday ishlaydi

lex.uz'da "o'zgargan hujjatlar ro'yxati" yo'q. Qonunga o'zgartirish alohida hujjat sifatida
chiqadi, masalan "Mehnat kodeksiga o'zgartirish kiritish to'g'risida"gi Qonun. Uning matnida
o'zgartirilgan hujjatga havola bo'ladi. Shundan keyin lex.uz asl hujjatning joriy tahririni
yangilaydi. Bu ba'zan bir necha kun, ba'zan oylar kechikadi.

**Haqiqiy misol (2026-11-07 da tekshirildi).** O'RQ-1186 (yong'in xavfsizligi) 02.11.2026 da
qabul qilingan, 05.02.2027 da kuchga kiradi. Uning matnida bazamizdagi uchta kodeksga havola bor:
MJtK (8 ta), JK va JPK. lex.uz'dagi MJtK sahifasining tepasida hozir banner turibdi:
**"Hujjatga o'zgartirish kiritilmoqda. Asos: O'RQ-1186"** (`div.lx_strip`). Matnning o'zi esa
hali eski. 05.11 da yuklangan 86 ta hujjatning hech birida bunday banner yo'q edi.

Demak lex.uz o'zgarish kelayotganini o'zi ko'rsatadi. Shuning uchun uch yo'l birga ishlatiladi:

1. **Yangi hujjatlar orqali (asosiy yo'l).** RSS o'qiladi, oldin ko'rilmagan har bir hujjat
   yuklab olinadi (kuniga ≈4 so'rov). Uning matnidagi havolalar orasida bizning bazamizdagi
   hujjat bo'lsa, o'sha hujjat **7 kun davomida har kecha** qayta tekshiriladi. Shu muddat
   ichida lex.uz yo matnni yangilaydi, yo banner qo'yadi. Yangi hujjatning o'zi qamrovga kirsa
   (hozir: Konstitutsiya va kodekslar; 6-bosqichda qonun, farmon va qarorlar), u bazaga
   qo'shiladi.
2. **Banner orqali.** Parser `lx_strip` bannerini o'qiydi: `pending_changes` (asos hujjat ID'si,
   nomi, sanasi). Banner turgan hujjat banner yo'qolguncha **har 2 kunda** qayta tekshiriladi.
   Banner kuchga kirish sanasigacha oylar turishi mumkin, shuning uchun har kecha emas.
   Banner foydalanuvchiga ham ko'rsatiladi: `get_article` va `get_document` javobida "⚠ lex.uz:
   hujjatga o'zgartirish kiritilmoqda (asos: O'RQ-1186, 02.11.2026), matn hali yangilanmagan"
   degan qator chiqadi. AI shuni hisobga olib javob beradi.
3. **Navbat bilan aylanib chiqish (zaxira yo'l).** Har kecha eng uzoq vaqt tekshirilmagan
   hujjatlar qayta yuklanadi. Bir kechada eng ko'pi bilan 400 ta so'rov yuboriladi (≈15 daqiqa).
   Hozirgi 86 ta hujjat har kecha to'liq tekshiriladi. To'liq korpusda (≈22 ming hujjat) bitta
   aylanish ≈110 kun oladi. Bu yo'l faqat 1- va 2-yo'l o'tkazib yuborgan holatlar uchun kerak:
   masalan, hujjat kuchini yo'qotgani boshqa hujjat orqali emas, kartochkada ko'rsatilgan bo'lsa.

Hujjatni qayta tekshirish: sahifa va kartochka yuklanadi, parse qilinadi, `index_document`
chaqiriladi. Mazmun o'zgarmagan bo'lsa (`content_hash` bir xil), baza o'zgartirilmaydi va
embedding qayta hisoblanmaydi. Hujjat kuchini yo'qotgan bo'lsa, uning faqat rekvizitlari qoladi.
Bu `index_document`da allaqachon bor. Hujjat bitta tranzaksiyada almashtiriladi, shuning uchun
yangilash paytida ham qidiruv ishlab turadi.

`pending_changes` `content_hash`ga kirmaydi va alohida `UPDATE` bilan yoziladi. Aks holda banner
paydo bo'lishi yoki yo'qolishi butun kodeksni (minglab bo'lak) qayta embedding qildirardi.

Matn haqiqatan o'zgarsa, hujjat to'liq qayta indekslanadi. Lekin matni o'zgarmagan bo'laklarning
vektorlari eski qatorlardan olinadi (bo'lak matni bo'yicha). Kodeksga kiritilgan o'zgartirish
odatda bir necha moddaga tegadi, shuning uchun embedding soniyalarda tugaydi.

Holat yangi `crawl_state` jadvalida saqlanadi (migratsiya `0006`):

```
crawl_state   doc_id PK, checked_at, changed_at, recheck_until, last_error
rss_seen      doc_id PK, title, seen_at, links (int[])
```

Buyruq: `qonunshunos update [--budget 400] [--dry-run]`. Oxirida hisobot qaytaradi: yangi,
o'zgargan, kuchini yo'qotgan va xato bergan hujjatlar. Bu hisobot ertalabki xabarga qo'shiladi.

Yangilash `myserver`ning o'zida ishlaydi. Embedding modeli alohida jarayonga yuklanadi
(≈300 MB). Ilovani siqib qo'ymaslik uchun: `MemoryMax=900M`, `CPUQuota=50%`, `Nice=10`.
Boshlang'ich `data/raw` va `data/parsed` Mac'dan bir marta `rsync` qilinadi, shunda birinchi kechada
lex.uz'dan 86 ta hujjat qayta yuklanmaydi.

## Tungi jadval (Toshkent vaqti)

| Vaqt | Qayerda | Ish | systemd unit |
|---|---|---|---|
| 03:30 | `myserver` | `qonunshunos update` | `qonunshunos-update.timer` |
| 04:30 | `myserver` | `qonunshunos auth-cleanup` | `qonunshunos-cleanup.timer` |
| 04:40 | `myserver` | `pg_dump -Fc` → `~/backups/qonunshunos_*.dump` | `qonunshunos-backup.timer` |
| 05:30 | `home` | `rsync myserver:~/backups/ → ~/backups/myserver/` | `backup-pull.timer` (user) |
| 08:00 | `myserver` | ertalabki hisobot Telegram'ga | `qonunshunos-report.timer` |
| har 5 daq. | `home` | `/healthz` tekshiruvi | `qonunshunos-watch.timer` (user) |

- Zaxira yangilashdan keyin olinadi, shuning uchun unda kechagi o'zgarishlar ham bo'ladi.
- `pg_backup.sh` o'zgartirilmaydi: `qonunshunos` uchun alohida unit repoda turadi
  (`deploy/`). `-Fc` formati siqilgan va `pg_restore` bilan tanlab tiklash mumkin.
- Qaror (2026-11-07): `home` `~/backups`ni **to'liq** tortadi (ochiqkurs, taklifnoma, media ham),
  chunki ular hozir faqat server diskida turibdi.
- `home` nusxani tortib olgandan keyin serverga `~/backups/.pulled` belgisini qo'yadi.
  Ertalabki hisobot shu belgiga qarab "oxirgi off-site nusxa: N soat oldin" deb yozadi. Shunday
  qilib, `home` o'chib qolsa ham bilinadi.

## Telegram xabarlari

- Qaror (2026-11-07): **yangi bot** (BotFather orqali, masalan `@qonunshunos_ops_bot`). Uni faqat siz ishlatasiz:
  xabarlar sizning chat ID'ingizga keladi. Token va chat ID serverdagi `.env`da va `home`dagi
  `~/.config/qonunshunos/watch.env`da saqlanadi, git'ga qo'shilmaydi.
- Kod: `qonunshunos.notify` (`httpx` bilan, yangi bog'liqlik kerak emas) va CLI
  `qonunshunos notify "matn"`. `home`dagi tekshiruv skripti faqat `curl` ishlatadi.
- Xabar namunasi:

  ```
  Qonunshunos · 08.11 hisobot
  Yangilash: 86 tekshirildi, 1 o'zgardi (Mehnat kodeksi), 0 xato
  RSS: 5 yangi hujjat, 1 tasi bizdagi hujjatga havola qiladi
  Foydalanuvchilar: 3 (kecha faol 2) · chaqiruvlar: 14 qidiruv, 41 boshqa
  Zaxira: 04:40 (21 MB) · home'ga: 05:31 · disk: 25 GB bo'sh
  ```

## Modullar va fayllar

| Fayl | Mazmuni |
|---|---|
| `src/qonunshunos/crawler/rss.py` | RSS'ni o'qish: ID, sarlavha, tur, sana |
| `src/qonunshunos/crawler/update.py` | `update`: RSS → havolalar → navbat → qayta tekshirish |
| `src/qonunshunos/db/migrations/0006_crawl_state.sql` | `crawl_state`, `rss_seen` |
| `src/qonunshunos/notify.py` | Telegram'ga yuborish, ertalabki hisobot |
| `deploy/systemd/*.service`, `*.timer` | `update`, `cleanup`, `backup`, `report`, `alert@` |
| `deploy/backup.sh` | `pg_dump -Fc`, tarkibini tekshirish, 14 kunlik tozalash. Parol argv'ga emas, `PGPASSWORD`ga |
| `deploy/home/` | `backup-pull`, `qonunshunos-watch` user unit'lari, `telegram.sh`, `install.sh` (Mac'dan ishga tushiriladi) |
| `deploy/root-setup.sh` | yangi unit'larni o'rnatish (siz sudo bilan ishga tushirasiz) |

## Ishlar tartibi

1. ✅ `rss.py` + testlar (`tests/fixtures`dagi qisqartirilgan RSS). Parser: `pending_changes`
   (`lx_strip`) + MJtK sahifasidan olingan fixture. `get_article`/`get_document`da ogohlantirish.
2. ✅ `0006` migratsiyasi, `update.py` + testlar (soxta `LexClient`, `-m db`).
3. ✅ `notify.py`, `qonunshunos notify` va `report` + testlar.
4. ✅ `deploy/` fayllari: zaxira skripti, systemd unit'lari, `home` skriptlari.
5. ✅ Siz: Telegram bot yaratib, token va chat ID'ni berasiz.
6. ✅ Server: `deploy.sh`, `data/` rsync, `root-setup.sh` (sudo bilan, siz ishga tushirasiz).
   `home`: user unit'larni o'rnatish. Har bir qadamdan oldin sizdan so'rayman.
7. ✅ Sinov: `update --dry-run`, keyin haqiqiy `update`. Zaxiradan tiklash sinovi. Saytni
   to'xtatib, ogohlantirish kelishini tekshirish. "Natija" bo'limi.

## Natija (2026-11-07)

**O'rnatildi.** `myserver`: `qonunshunos-update` (03:30), `-cleanup` (04:30), `-backup` (04:40),
`-report` (08:00) timer'lari, har biri xato bilan tugasa `qonunshunos-alert@` Telegram'ga
yozadi. `home`: `qonunshunos-watch` (har 5 daqiqa) va `backup-pull` (05:30) user timer'lari.
Bot: @qonunshunosbot, xabarlar faqat operatorning shaxsiy chatiga keladi.

**Birinchi haqiqiy yangilash** (`myserver`, 294 so'rov, ≈10 daqiqa, xatosiz):

- RSS'dagi 120 ta yangi hujjatdan 34 tasi bizdagi hujjatlarga havola qiladi. Eng ko'p
  bog'langan hujjat O'RQ-1180 (bolalarni zo'ravonlikdan himoya qilish): 8 ta hujjatimizga,
  jumladan MK, JK, JPK va MJtK'ga havola qiladi.
- **5 ta hujjatda "o'zgartirish kiritilmoqda" banneri** topildi: MJtK, JPK, Aholi bandligi,
  Ta'lim, Huquqbuzarliklar profilaktikasi to'g'risidagi qonunlar. 05.11 dagi yuklashda ularning
  birortasida ham banner yo'q edi. Endi bu hujjatlarning moddalarida ogohlantirish chiqadi.
- **Topilgan xato:** 11 ta hujjat "o'zgardi" deb chiqdi, lekin ularning matni o'zgarmagan edi
  (embedding: Jinoyat kodeksida 5 ta, qolganlarida 0 ta bo'lak qayta hisoblandi). Sababi:
  lex.uz kartochkani har safar boshqa tilda beradi (o'zbek kirill, lotin yoki rus:
  `Кодекс`/`Kodeks`, `Амалда`/`Действующий`). Endi `content_hash` kartochkadan faqat tilga
  bog'liq bo'lmagan maydonlarni oladi (`CARD_HASH_FIELDS`). Saqlangan hash'lar serverda
  `qonunshunos index` bilan bir marta yangilandi: 46 soniya, birorta bo'lak qayta hisoblanmadi.
- **Ikkinchi xato:** kodeksga o'xshagan, lekin qamrovdan tashqaridagi yangi hujjatning
  (VM qarori 585) parse fayli `data/parsed`da qolib ketgan, `index` esa uni bazaga qo'shgan.
  Endi bunday fayl o'chiriladi, qaror bazadan olib tashlandi.

**Zaxira:** 41 MB dump, tarkibi tekshiriladi. `home`ga birinchi ko'chirish 109 MB (boshqa
ilovalarning 14 kunlik nusxalari bilan), keyin serverga `.pulled` belgisi qo'yildi. Tiklash
sinovi yuqorida ("Zaxiradan tiklash").

**Monitoring sinovi:** ilova 07:50:44 da to'xtatildi. `home` ikki marta ketma-ket `502` oldi va
2-xatoda (08:00) "🔴 ishlamayapti" deb yozdi. Ilova qayta ishga tushirildi, keyingi tekshiruvda
"✅ yana ishlayapti" xabari keldi. Ertalabki hisobot va xato ogohlantirishi namunasi ham
Telegram'ga yuborildi.

**O'rnatishda chiqqan muammolar:**

- macOS'dagi `openrsync` bir nechta manba faylni berganda ba'zilarini jimgina tashlab
  ketdi. `deploy/home/install.sh` endi `tar` ishlatadi va fayllar joyidaligini tekshiradi.
- `home`ning SSH sozlamalarida `myserver` nomi yo'q. Server manzili `watch.env`da
  (`MYSERVER_SSH`), repoda emas.
- Claude Code'ning avtomatik rejimi production deploy'ni blokladi, birinchi `deploy.sh`ni
  foydalanuvchi o'zi ishga tushirdi.

**Keyin kuzatiladi:** birinchi tungi ishlar (xotira, vaqt), ertalabki hisobotda "oʻzgardi"
soni (endi faqat haqiqiy o'zgarishlar bo'lishi kerak), claude.ai'ning ≈240 soniyalik
so'rovlari (4-bosqich "Natija").

## Zaxiradan tiklash

2026-11-07 da Mac'da sinaldi: 41 MB dump 9 soniyada tiklandi, 86 hujjat, 16 657 bo'lak,
`search` ishladi.

```
createdb qonunshunos_restore
pg_restore --no-owner --dbname=qonunshunos_restore qonunshunos_YYYYmmdd_HHMMSS.dump
QONUNSHUNOS_DSN=postgresql://…/qonunshunos_restore uv run qonunshunos search "yillik taʼtil"
```

Serverda to'liq tiklash: `qonunshunos` xizmatini to'xtatish, bazani `dropdb`/`createdb` bilan
qayta yaratish (`root-setup.sh` 2-qadami: rol, `vector` va `pg_trgm` kengaytmalari),
`pg_restore`, xizmatni ishga tushirish. Bitta jadvalni tiklash: `pg_restore -t users …`.

## Xavflar

- **lex.uz tahrirni kechiktirib kiritadi.** Shuning uchun 7 kunlik qayta tekshirish va navbat
  bilan aylanib chiqish bor. Baribir bir necha kunlik kechikish bo'lishi mumkin. Har bir
  javobdagi "hujjat tahriri dd.mm.yyyy" yozuvi buni foydalanuvchiga ko'rsatib turadi.
- **Havola bo'lmagan o'zgarishlar.** Ba'zi o'zgartirish hujjatlari matnida havola bo'lmasligi
  mumkin. Ularni faqat aylanib chiqish ushlaydi. 6-bosqichda (to'liq korpus) buni o'lchab,
  kerak bo'lsa byudjetni oshiramiz.
- **RSS faqat bir oyni ko'rsatadi.** Server bir oydan ko'proq o'chib qolsa, RSS'dagi yangiliklar
  o'tkazib yuboriladi. U holda `listing` bilan qo'lda to'ldiriladi.
- **Xotira.** Ilova (≈540 MB) va yangilash (≈300 MB) bir vaqtda ishlaydi. Boshqa ilovalar ham
  bor. Cheklovlar unit'larda belgilanadi, birinchi kechalarda `journalctl` bilan kuzatiladi.
- **Tekshiruvni `home` qiladi.** `home` o'chib qolsa, sayt to'xtaganini hech kim bilmaydi. Buning
  oldini olish uchun ertalabki hisobot "home'ga oxirgi ko'chirish"ni ko'rsatadi: hisobot kelmasa
  yoki shu vaqt eski bo'lsa, demak `home` yoki server ishlamayapti.
