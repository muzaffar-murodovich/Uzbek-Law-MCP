# 5-bosqich: zaxira nusxa, monitoring, kunlik yangilash

Holat (2026-11-07): 🔨 dizayn tasdiqlandi, kod yozilmoqda. Tegishli hujjatlar:
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
yangilaydi. Bu ba'zan bir necha kun kechikadi. Shuning uchun ikki yo'l birga ishlatiladi:

1. **Yangi hujjatlar orqali (asosiy yo'l).** RSS o'qiladi, oldin ko'rilmagan har bir hujjat
   yuklab olinadi (kuniga ≈4 so'rov). Uning matnidagi havolalar orasida bizning bazamizdagi
   hujjat bo'lsa, o'sha hujjat **7 kun davomida har kecha** qayta tekshiriladi. Shu bilan lex.uz
   tahrirni kechiktirib kiritsa ham, o'zgarish o'tkazib yuborilmaydi. Yangi hujjatning o'zi
   qamrovga kirsa (hozir: Konstitutsiya va kodekslar; 6-bosqichda qonun, farmon va qarorlar),
   u bazaga qo'shiladi.
2. **Navbat bilan aylanib chiqish (zaxira yo'l).** Har kecha eng uzoq vaqt tekshirilmagan
   hujjatlar qayta yuklanadi. Bir kechada eng ko'pi bilan 400 ta so'rov yuboriladi (≈15 daqiqa).
   Hozirgi 86 ta hujjat har kecha to'liq tekshiriladi. To'liq korpusda (≈22 ming hujjat) bitta
   aylanish ≈110 kun oladi. Bu yo'l faqat 1-yo'l o'tkazib yuborgan holatlar uchun kerak:
   masalan, hujjat kuchini yo'qotgani boshqa hujjat orqali emas, kartochkada ko'rsatilgan bo'lsa.

Hujjatni qayta tekshirish: sahifa va kartochka yuklanadi, parse qilinadi, `index_document`
chaqiriladi. Mazmun o'zgarmagan bo'lsa (`content_hash` bir xil), baza o'zgartirilmaydi va
embedding qayta hisoblanmaydi. Hujjat kuchini yo'qotgan bo'lsa, uning faqat rekvizitlari qoladi.
Bu `index_document`da allaqachon bor. Hujjat bitta tranzaksiyada almashtiriladi, shuning uchun
yangilash paytida ham qidiruv ishlab turadi.

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
| `deploy/backup.sh` | `pg_dump -Fc`, tekshirish, 14 kunlik tozalash |
| `deploy/home/` | `backup-pull` va `qonunshunos-watch` user unit'lari va skriptlari |
| `deploy/root-setup.sh` | yangi unit'larni o'rnatish (siz sudo bilan ishga tushirasiz) |

## Ishlar tartibi

1. `rss.py` + testlar (`tests/fixtures`dagi qisqartirilgan RSS).
2. `0006` migratsiyasi, `update.py` + testlar (soxta `LexClient`, `-m db`).
3. `notify.py`, `qonunshunos notify` va `report` + testlar.
4. `deploy/` fayllari: zaxira skripti, systemd unit'lari, `home` skriptlari.
5. Siz: Telegram bot yaratib, token va chat ID'ni berasiz.
6. Server: `deploy.sh`, `data/` rsync, `root-setup.sh` (sudo bilan, siz ishga tushirasiz).
   `home`: user unit'larni o'rnatish. Har bir qadamdan oldin sizdan so'rayman.
7. Sinov: `update --dry-run`, keyin haqiqiy `update`. Zaxiradan tiklash sinovi. Saytni bir daqiqaga
   to'xtatib, ogohlantirish kelishini tekshirish. "Natija" bo'limi.

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
