# 4-bosqich: OAuth, Google orqali kirish, limitlar

Holat (2026-11-06): 🔨 kod tayyor (1–6-qadamlar), Google sozlamalari va `myserver`dagi sinov kutilmoqda. Tegishli hujjatlar: [PLAN.md](../PLAN.md)
(1-, 5- va 7-bo'limlar), [3-bosqich](stage3-mcp-server.md).

## Maqsad

Hozir `/mcp`ga istalgan odam kira oladi va hech qanday cheklov yo'q. Bu bosqichda:

1. Server o'zining **OAuth 2.1 avtorizatsiya serverini** oladi. claude.ai, ChatGPT, Claude Code
   va Cursor konnektor qo'shilganda foydalanuvchini kirish sahifasiga yuboradi, so'ng token
   olib, har bir so'rovga qo'shadi.
2. Foydalanuvchi **Google** orqali kiradi. Parol saqlanmaydi. Telegram orqali kirish keyinroq
   qo'shiladi (qaror 2026-11-06, pastda "Telegram (keyinroq)" bo'limi).
3. Har bir chaqiruv foydalanuvchiga bog'lanadi va **limitlar** ishlaydi: kuniga 30 ta
   `search_law`, 200 ta boshqa chaqiruv, daqiqasiga 10 ta.
4. Administrator CLI orqali foydalanuvchilarni ko'radi, limit beradi va bloklaydi.

Oddiy qilib aytganda: OAuth — mehmonxona kartasi kabi. Foydalanuvchi bir marta ro'yxatdan o'tadi
(Google — pasport), AI yordamchi esa karta (token) oladi va har safar shu karta bilan
kiradi. Karta muddati tugasa, yangisi so'raladi. Karta kimniki ekani ma'lum bo'lgani uchun
limitlarni hisoblash mumkin.

## Tayyor bo'lish mezonlari

- `/.well-known/oauth-protected-resource/mcp` va `/.well-known/oauth-authorization-server`
  to'g'ri metama'lumot qaytaradi. Tokensiz `/mcp` so'roviga `401` va `WWW-Authenticate` sarlavhasi
  qaytadi.
- Dynamic Client Registration (`/register`), PKCE (S256), `/authorize`, `/token`
  (`authorization_code` va `refresh_token`), `/revoke` ishlaydi.
- `/authorize` sahifasida "Google orqali kirish" tugmasi bor va u haqiqiy akkaunt bilan
  sinalgan.
- Limitlar ishlaydi va oshib ketganda o'zbekcha xabar qaytadi (xato emas). Hisoblagich
  Toshkent vaqti bilan 00:00 da nolga tushadi.
- `usage_events.user_id` to'ldiriladi.
- Admin CLI: `qonunshunos user list|show|limit|block|unblock`. Akkauntlarni birlashtirish yo'q.
- Maxfiylik siyosati va foydalanish shartlari sahifalari bor (Google buni talab qiladi).
- **Haqiqiy mijozlar bilan sinov:** Claude Code, claude.ai va ChatGPT konnektor sifatida
  ulanadi, kiradi va savolga javob oladi. Natija "Natija" bo'limiga yoziladi.
- Mahalliy ishlab chiqishda auth o'chirilishi mumkin (`--no-auth`, `--stdio` doim auth'siz).
- `uv run pytest` o'tadi. To'liq OAuth oqimi SDK'ning OAuth mijozi bilan testda tekshiriladi.

## Texnologiyalar

- **MCP SDK'ning o'z auth qismi** (`mcp.server.auth`). U `/.well-known/...`, `/authorize`,
  `/token`, `/register`, `/revoke` marshrutlarini, PKCE tekshiruvini va bearer token
  middleware'ini tayyor beradi. Biz faqat `OAuthAuthorizationServerProvider` interfeysini
  yozamiz: mijozlar, kodlar va tokenlarni bazada saqlash hamda kirish sahifasi. `MCPServer`ga
  `auth=AuthSettings(...)` va `auth_server_provider=...` beriladi.
- **Yangi bog'liqlik yo'q.** Google bilan gaplashish uchun `httpx` (SDK bilan birga keladi).
  Sahifalar oddiy HTML shablon (`string.Template`), Jinja kerak emas.
- **Tokenlar — tasodifiy satr (opaque), JWT emas.** Bazada faqat ularning SHA-256 xeshi
  saqlanadi. Server bitta, shuning uchun JWT'ning afzalligi (bazasiz tekshirish) bizga kerak emas.
  Opaque token esa darhol bekor qilinadi (blok, chiqish). Har bir so'rovda bitta indeksli
  `SELECT` bo'ladi, bu ≈1 ms.

## Kirish oqimi

```
AI mijoz (claude.ai)            Qonunshunos                         Google          
   │ POST /mcp (tokensiz)  ───►  401 + resource metadata havolasi
   │ GET /.well-known/...  ───►  metama'lumot
   │ POST /register        ───►  client_id (DCR)
   │ brauzer: /authorize?client_id&redirect_uri&code_challenge&state&resource
   │                       ───►  auth_requests'ga yoziladi, kirish sahifasi:
   │                              [Google orqali kirish]
   │                                   │ Google ─────────────────────► accounts.google.com
   │                                   │ ◄── /auth/google/callback?code ──┘
   │                              foydalanuvchi topiladi yoki yaratiladi
   │                              rozilik sahifasi (shu ilova birinchi marta bo'lsa)
   │ ◄── redirect_uri?code&state
   │ POST /token (code + code_verifier) ───► access (1 soat) + refresh (60 kun)
   │ POST /mcp, Authorization: Bearer …  ───► tool'lar
```

- **`auth_requests`**: `/authorize` kelganda uning parametrlari (client, redirect_uri,
  code_challenge, state, scope, resource) bazaga 10 daqiqaga yoziladi. Kirish sahifasi va
  Google callback'i shu yozuvning tasodifiy ID'si bilan ishlaydi. Shunda server
  qayta ishga tushsa ham oqim uzilmaydi.
- **Rozilik sahifasi.** DCR orqali har kim mijoz ro'yxatdan o'tkaza oladi va istalgan nom
  qo'yadi. Shuning uchun foydalanuvchiga "«Claude» (claude.ai) sizning nomingizdan
  Qonunshunos'dan foydalanmoqchi. Ruxsat berasizmi?" deb so'raladi. Nom yonida `redirect_uri`
  domeni ko'rsatiladi, chunki nomni soxtalashtirish mumkin, domenni esa yo'q. Bir marta ruxsat
  berilgan mijoz uchun sahifa qayta chiqmaydi (`oauth_consents`).
- **`redirect_uri`**: faqat `https://…` yoki `http://localhost` / `127.0.0.1` (Claude Code,
  Cursor). `/authorize`dagi `redirect_uri` ro'yxatdan o'tgan bilan aynan mos bo'lishi kerak
  (SDK tekshiradi).
- **Tokenlar:** access token 1 soat, refresh token 60 kun. Refresh har ishlatilganda
  almashtiriladi (rotation): eski refresh bekor bo'ladi. Avtorizatsiya kodi 5 daqiqa va bir
  martalik. `resource` (RFC 8707) tokenga yoziladi va `/mcp` uni tekshiradi
  (`validate_token_resource=True`).
- **Scope** bitta: `qonunshunos`. Kelajakda pullik tarif scope bilan emas, `users.plan` bilan
  belgilanadi.
- **Client ID Metadata Documents (CIMD).** MCP spetsifikatsiyasining yangi tahririda DCR'ning
  o'rniga tavsiya qilinadi (mijoz o'z metama'lumotini URL sifatida beradi). SDK serverda uni
  hali qo'llab-quvvatlamaydi, mijozlar esa DCR bilan ishlaydi. Shuning uchun hozircha faqat DCR.
  Keyinroq `get_client` URL ko'rinishidagi `client_id`ni yuklab olishi bilan qo'shiladi.

## Google

- **OpenID Connect**, ruxsatlar faqat `openid email profile`. Bular "nozik bo'lmagan" ruxsatlar,
  shuning uchun Google tekshiruvi (verification) talab qilinmaydi. Ilovani "Production" holatiga
  o'tkazish kifoya (aks holda refresh token 7 kunda o'ladi va faqat test foydalanuvchilar kira
  oladi).
- Oqim: `/auth/google/start?req=<id>` → `accounts.google.com` (`state`, `nonce`, PKCE bilan) →
  `/auth/google/callback` → kod `oauth2.googleapis.com/token`da almashtiriladi.
- **ID token tekshiruvi:** token Google'ning o'zidan TLS orqali to'g'ridan-to'g'ri olingani
  uchun, OIDC qoidasiga ko'ra imzoni tekshirmasa ham bo'ladi (JWKS va kriptografik kutubxona
  kerak emas). Lekin `iss`, `aud` (bizning client_id), `exp`, `nonce` va `email_verified`
  tekshiriladi.
- Saqlanadi: `sub` (doimiy ID), email, ism. Google tokenlari saqlanmaydi: bizga faqat "bu kim"
  degan javob kerak.

## Telegram (keyinroq)

Qaror (2026-11-06): hozircha faqat Google. Telegram keyin qo'shilganda Telegram Login Widget
ishlatiladi: BotFather'da alohida bot, `/setdomain`, javob bot tokeni bilan HMAC-SHA256 orqali
tekshiriladi, `auth_date` 10 daqiqadan eski bo'lmasligi kerak. Kirish sahifasi va
`user_identities` (`provider` ustuni) bunga hozirdan tayyor.

## Akkauntlar

- Birinchi kirishda `users` va `user_identities` yozuvi yaratiladi. Keyingi safar
  (`provider`, `subject`) bo'yicha topiladi.
- **Bir nechta provayderni bitta akkauntga ulash** (PLAN, 7-bo'lim) keyinroq hal qilinadi
  (2026-11-06). Jadval tuzilmasi (`user_identities`) bunga hozirdan tayyor.
- Bloklangan foydalanuvchi kira olmaydi, uning tokenlari esa darhol ishlamay qoladi.

## Limitlar

- **Qanday hisoblanadi:** kunlik son `usage_events`dan olinadi:
  `count(*) WHERE user_id = $1 AND ts >= <Toshkent vaqti bilan bugun 00:00> AND counted`.
  `(user_id, ts)` indeksi bor, kuniga ko'pi bilan 230 qator, shuning uchun so'rov ≈1 ms. Alohida
  hisoblagich jadvali kerak emas va statistika bilan limit hech qachon farq qilmaydi.
- **Daqiqalik limit** xotirada hisoblanadi (har bir foydalanuvchi uchun oxirgi chaqiruvlar
  vaqti). Jarayon bitta, shuning uchun bu yetarli. Qayta ishga tushganda nolga tushishi muammo
  emas.
- **Guruhlar:** `search` (`search_law`), `other` (`get_article`, `get_document`, `get_section`,
  `find_document`, resurslar). `list_codes` limitsiz, lekin daqiqalik limitga kiradi.
- **Qiymatlar** konfiguratsiyada: `plans = {"free": {"search": 30, "other": 200,
  "per_minute": 10}}`. `users.limits_override` (jsonb) tarif qiymatining ustidan yoziladi.
  Masalan, `{"search": 100}` faqat qidiruv limitini o'zgartiradi.
- **Limit tugaganda** tool xato qaytarmaydi, o'zbekcha matn qaytaradi. AI uni foydalanuvchiga
  tushuntiradi:
  > Bugungi bepul limit tugadi: kuniga 30 ta qidiruv. Hisoblagich Toshkent vaqti bilan 00:00 da
  > (≈5 soatdan keyin) yangilanadi. Bu orada lex.uz saytidan foydalanishingiz mumkin.
  Daqiqalik limit uchun: "Juda tez-tez so'rov: bir daqiqa kutib, qayta urinib ko'ring."
  Bunday chaqiruv `usage_events`ga `counted=false` bilan yoziladi.
- Tekshiruv `Services.run` ichida, tool ishlashidan oldin bo'ladi. Foydalanuvchi
  `get_access_token().subject`dan olinadi (kontekst o'zgaruvchisi `anyio` oqimiga ham o'tadi,
  tekshirildi).
- **Serverni himoya qilish:** `/register`, `/authorize`, `/token` uchun IP bo'yicha cheklov nginx
  `limit_req` bilan qo'yiladi (5-bosqich). Hech qachon kirmagan DCR mijozlari 1 kundan keyin
  tozalanadi.

## Ma'lumotlar modeli (migratsiya 0005)

```
users            id, display_name, email, plan ('free'), limits_override jsonb,
                 created_at, last_seen_at, blocked_at, blocked_reason
user_identities  user_id, provider ('google'|'telegram'), subject, email, username,
                 created_at;  UNIQUE (provider, subject)
oauth_clients    client_id, info jsonb (DCR metama'lumoti va mijoz siri: SDK uni ochiq solishtiradi),
                 created_at, last_used_at
auth_requests    id, client_id, params jsonb, created_at, expires_at   -- 10 daqiqa
oauth_codes      code_hash, client_id, user_id, params jsonb, expires_at   -- 5 daqiqa
oauth_tokens     token_hash, kind ('access'|'refresh'), client_id, user_id, scopes,
                 resource, expires_at, revoked_at, created_at
oauth_consents   user_id, client_id, created_at;  PK (user_id, client_id)
usage_events     + counted boolean NOT NULL DEFAULT true; user_id → users(id)
```

Muddati o'tgan kodlar, so'rovlar va tokenlar har kuni tozalanadi (5-bosqichdagi worker
timer'iga qo'shiladi, hozircha `qonunshunos auth-cleanup` buyrug'i).

## Sahifalar

Hammasi o'zbekcha, oddiy va yengil (CSS ichida, JS yo'q):

| Manzil | Mazmuni |
|---|---|
| `/` | Qisqa tavsif: bu nima, qanday ulanadi (claude.ai, ChatGPT, Claude Code uchun qadamlar), lex.uz'ga havola |
| `/authorize` → kirish | Ikkita tugma, xizmat bepul ekani, maxfiylik siyosatiga havola |
| `/auth/consent` | "X ilovasi … ruxsat berasizmi?" |
| `/maxfiylik` | Maxfiylik siyosati: nima saqlanadi (email va ism, so'rovlar matni ≤300 belgi, vaqt), nima uchun (limit, statistika, sifatni yaxshilash), qancha vaqt, kimga berilmaydi, qanday o'chirish so'raladi |
| `/shartlar` | Foydalanish shartlari: yuridik maslahat emas, manba lex.uz, suiiste'mol taqiqlanadi |

Google consent screen uchun ilova nomi, logotip (ixtiyoriy), `/maxfiylik` va `/shartlar`
havolalari kerak.

## Konfiguratsiya (`.env`)

```
QONUNSHUNOS_PUBLIC_URL=https://qonunshunos.muzaffar.zip   # issuer va resource shundan
QONUNSHUNOS_CONTACT=...           # /maxfiylik va /shartlar'dagi murojaat manzili
GOOGLE_CLIENT_ID=... / GOOGLE_CLIENT_SECRET=...
```

`qonunshunos serve` auth'ni sozlamalar bo'lsa yoqadi. `--no-auth` faqat `127.0.0.1`da
ishlaganda ruxsat etiladi. Mahalliy ishlab chiqish uchun `QONUNSHUNOS_DEV_LOGIN=1` kirish
sahifasiga "Test foydalanuvchi sifatida kirish" tugmasini qo'shadi (faqat localhost'da). Shunda
testlar va mahalliy sinov Google'siz ishlaydi.

## Modullar

```
src/qonunshunos/auth/
  provider.py   OAuthAuthorizationServerProvider: mijozlar, kodlar, tokenlar (Postgres)
  google.py     OIDC: start URL, kodni almashtirish, ID token tekshiruvi
  users.py      foydalanuvchini topish/yaratish, blok
  limits.py     tarif, kunlik va daqiqalik hisob, xabar matnlari
  pages.py      HTML sahifalar va /auth/* marshrutlari
db/migrations/0005_auth.sql
```

`mcp/server.py` o'zgarishlari: `AuthSettings`, provider, `custom_route`lar va `Services.run`da
limit tekshiruvi hamda `user_id`.

## Testlar

- `google`: ID token da'volarini tekshirish (soxta token, `httpx.MockTransport`), noto'g'ri `aud`,
  `nonce`, `email_verified=false`.
- `limits`: Toshkent kunining chegarasi (23:59 / 00:01), override, daqiqalik oyna, xabar matni.
- `-m db`: provider (kod bir martalik, refresh rotation, bekor qilingan token, bloklangan
  foydalanuvchi), limit tugaganda tool matni va `counted=false`.
- **To'liq oqim:** ASGI ilova + SDK'ning `OAuthClientProvider` mijozi. Kirish qismi soxta
  Google bilan (`MockTransport`). Mijoz ro'yxatdan o'tadi, kiradi, token oladi, `search_law`ni
  chaqiradi, tokenni yangilaydi.

## Haqiqiy mijozlar bilan sinov va `myserver`

claude.ai va ChatGPT konnektorlari faqat ommaviy HTTPS manzil bilan ishlaydi. Shuning uchun bosqich oxirida server `myserver`ga
**sinov tarzida** qo'yiladi: systemd xizmati, nginx sayti va Let's Encrypt sertifikati
`qonunshunos.muzaffar.zip` uchun, PGDG'dan pgvector va namunaviy korpus (22 ta kodeks + 65 ta
qonun). Bu 5-bosqichning bir qismini oldinroq bajaradi; zaxira nusxa, monitoring va kunlik
yangilash 5-bosqichda qoladi (roziligi 2026-11-06). `myserver`da har bir o'zgarishdan oldin ruxsat so'raladi.

Sinov rejasi:

1. Claude Code: `claude mcp add --transport http qonunshunos https://qonunshunos.muzaffar.zip/mcp`,
   `/mcp` → kirish → bitta savol.
2. claude.ai: Settings → Connectors → custom connector, Google bilan kirish, savol.
3. ChatGPT: developer mode'da konnektor, Google bilan kirish, savol.
4. Limit: `limits_override` bilan 2 ta qidiruv qo'yib, uchinchisida xabar chiqishini tekshirish.
5. Blok: `qonunshunos user block` → keyingi so'rov `401`.

## Foydalanuvchi bajaradigan ishlar

Bularni men qila olmayman (akkauntlar sizniki):

1. **Google Cloud:** loyiha → OAuth consent screen (External, nom, email, `/maxfiylik`,
   `/shartlar`) → Credentials → OAuth client ID (Web application). Redirect URI'lar:
   `https://qonunshunos.muzaffar.zip/auth/google/callback` va
   `http://localhost:8000/auth/google/callback`. So'ng ilovani "Production"ga o'tkazish.
   Client ID va secret `.env`ga.
2. `myserver`dagi o'zgarishlarga ruxsat (sinov deploy'i).

## Ishlar tartibi

1. ✅ `0005` migratsiyasi, `users.py`, `limits.py` + testlar (tashqi xizmatlarsiz).
2. ✅ `provider.py` (DCR, kodlar, tokenlar) + `-m db` testlari.
3. ✅ `pages.py`: kirish va rozilik sahifalari, dev login; `server.py`ga ulash; SDK mijozi bilan
   to'liq oqim testi.
4. ✅ `google.py` + testlar. Google'ni localhost'da haqiqiy akkaunt bilan sinash.
5. ✅ Limitlarni `Services.run`ga ulash, admin CLI.
6. ✅ `/`, `/maxfiylik`, `/shartlar` sahifalari.
7. ✅ `myserver`ga sinov deploy'i. ⏳ claude.ai va ChatGPT bilan sinov,
   "Natija" bo'limi, PLAN.md yangilanadi.

## Bajarilganlar va dizayndan farqlar (2026-11-06)

- 1–6-qadamlar bajarildi: `auth/` (`users`, `limits`, `provider`, `google`, `pages`),
  `site.py` (`/`, `/maxfiylik`, `/shartlar`), `0005` migratsiyasi, `serve` OAuth bilan,
  `qonunshunos user list|show|limit|block|unblock` va `qonunshunos auth-cleanup`. Testlar:
  157 ta. Ular orasida SDK'ning OAuth mijozi bilan to'liq oqim testi (ro'yxatdan o'tish → dev
  login → rozilik → token → tool → limit) va soxta Google bilan callback testi bor.
- **Mijoz siri** xesh qilinmaydi: SDK uni ochiq matn bilan solishtiradi. Bu xavfli emas, chunki
  oqimni baribir PKCE himoya qiladi. Kodlar va tokenlar esa faqat xesh ko'rinishida saqlanadi.
- **Rozilikni soxtalashtirishdan himoya:** kirgandan keyin foydalanuvchi `auth_requests`ga
  server tomonida bog'lanadi. Rozilik formasi esa faqat o'sha sahifada ko'rsatilgan bir
  martalik token bilan qabul qilinadi. Google callback'i `qs_req` cookie orqali kirish
  boshlangan brauzerga bog'langan (login CSRF'dan himoya).
- `QONUNSHUNOS_SECRET` kerak bo'lmadi: hamma holat bazada saqlanadi.
- `resource` yubormaydigan mijozlar uchun `resource` avtomatik `<public_url>/mcp` qilib
  qo'yiladi, aks holda `validate_token_resource` ularning tokenini rad etardi.
- `serve` endi standart holatda OAuth talab qiladi. `--no-auth` faqat loopback'da ishlaydi
  (`scripts/e2e_claude.sh` shu bilan ishlaydi), `--stdio` esa doim auth'siz. Nginx ortidagi
  Host uchun SDK'ning DNS-rebinding himoyasiga ommaviy host qo'shiladi.
- **Shaxsiy ma'lumotlar qayerda saqlanishi** (o'z serverimiz orqali tekshirildi):
  "Shaxsga doir maʼlumotlar toʻgʻrisida"gi Qonunning 27¹-moddasi (OʻRQ-1125, 26.03.2026
  tahriri) O'zbekiston hududida saqlashni faqat biometrik, genetik va telekom operatorlari
  ma'lumotlari uchun majburiy qiladi. Qolgan ma'lumotlar chet elda shartlar bilan saqlanishi
  mumkin: davlat "bir xil himoya" ro'yxatida bo'lishi, standart shartnoma shartlari yoki xalqaro
  standartlar. 15-modda bo'yicha esa subyektning roziligi bilan ham uzatish mumkin. Shuning uchun
  kirish sahifasida va `/maxfiylik`da ma'lumot Germaniyada saqlanishi ochiq yoziladi va kirish
  shunga rozilik deb hisoblanadi. Germaniya Vazirlar Mahkamasi ro'yxatida bormi, tekshirilmagan.
  Ommaga ochishdan oldin buni yurist bilan tasdiqlash kerak (6-bosqich).

### Mahalliy sinov: haqiqiy Google va Claude Code (2026-11-06)

- **Google Cloud:** OAuth client (Web application), redirect URI'lar domendagi va
  `localhost:8000`dagi `/auth/google/callback`. Ilova **In production** holatida. Google
  "Publish app"ni Branding'dagi bosh sahifa, maxfiylik va shartlar havolalari to'ldirilmaguncha
  o'chiq ushlab turgan edi. Logotip va nozik ruxsatlar yo'q, shuning uchun tekshiruv talab
  qilinmadi. Havolalar server deploy qilingandan keyin ochiladi (7-qadam).
- **Claude Code** (`/mcp` → Authenticate) `http://localhost:8000/mcp`ga ulandi. Oqim:
  `401` → `/register` → `/authorize` → Google → rozilik sahifasi → `/token`. Foydalanuvchi
  Google ismi va emaili bilan yaratildi, tokenga `resource=http://localhost:8000/mcp` yozildi.
- Headless Claude Code saqlangan token bilan "Mehnat ta'tili necha kun?" savoliga javob berdi:
  MK 217- va 218-moddalarga havola qilib, 21 kun. `usage_events`ga 4 ta chaqiruv (1 ta qidiruv,
  3 ta modda) foydalanuvchi bilan yozildi. `qonunshunos user show 1`: search 1/30, other 3/200.
- Mahalliy sinovda `public_url` `http://localhost:8000` bo'lishi kerak: Google'dagi redirect
  shunday yozilgan. MCP konnektori ham `localhost` bilan qo'shiladi (`127.0.0.1` emas), aks holda
  `resource` mos kelmaydi.
- **Deploy'dan oldin:** uvicorn access log'i so'rov qatorini to'liq yozadi. Unga Google'ning bir
  martalik `code`i ham tushadi. Production'da access log o'chiriladi yoki so'rov parametrlarisiz
  yoziladi (nginx log'i yetarli).

### `myserver`ga sinov deploy'i (2026-11-06)

- `deploy/root-setup.sh` (sudo bilan bir marta, foydalanuvchi ishga tushiradi), `deploy/deploy.sh`
  (kod, bog'liqliklar, migratsiya, restart), `deploy/qonunshunos.service`,
  `deploy/nginx-qonunshunos.conf`. Ilova `/home/deploy/qonunshunos`da, `127.0.0.1:8100`da
  ishlaydi, ≈540 MB RAM oladi (`MemoryMax=1200M`).
- **pgvector:** PGDG paketi PGDG'ning PostgreSQL build'ini talab qiladi
  (`Breaks: postgresql-16-jit-llvm`), bu esa boshqa ilovalar bilan umumiy klasterni yangilab,
  qayta ishga tushirgan bo'lardi. Shuning uchun 0.8.7 manba kodidan, Ubuntu'ning
  `postgresql-server-dev-16` bilan yig'ildi. Arxiv SHA-256 bilan tekshiriladi.
- **TLS va proksi:** UFW 80/443 portlarni faqat Cloudflare'ga ochgan, shuning uchun Let's
  Encrypt HTTP-01 ishlamadi. Sayt boshqa saytlar kabi Cloudflare proksisi ortida ishlaydi:
  `*.muzaffar.zip` Origin sertifikati, "Full (strict)". nginx mijoz IP'sini
  `CF-Connecting-IP`dan oladi (faqat shu saytda), log'ga faqat yo'l yoziladi.
  Proksi 6-bosqich o'rniga hozir yoqildi.
- **Korpus:** Mac'da hisoblanib, SSH tunnel orqali yozildi: 86 ta hujjat, 16 657 ta bo'lak.
- **Tashqi tekshiruv:** `/`, `/maxfiylik`, `/shartlar`, metama'lumot — 200; tokensiz `/mcp` — 401
  va `WWW-Authenticate`.
- SSH: ko'p yangi ulanishdan keyin server ulanishni bir muddat rad etadi (fail2ban yoki UFW
  limit). `deploy.sh` shuning uchun bitta umumiy ulanish (ControlMaster) ishlatadi.

## Xavflar

- **Mijozlar OAuth'ni turlicha amalga oshiradi.** claude.ai, ChatGPT va Claude Code'ning har
  birida o'z xususiyati bor (`resource` parametri, refresh, `localhost` redirect). Shuning uchun
  uchalasi ham haqiqiy serverda sinaladi. Muammo chiqsa, `/authorize` va `/token` so'rovlari
  log'ga yoziladi (tokenlarsiz).
- **SDK 2.x auth API'si o'zgarishi mumkin** (masalan, `validate_token_resource` 3.0 da standart
  bo'ladi). Versiya `uv.lock`da qotirilgan.
- **DCR spam.** Har kim mijoz ro'yxatdan o'tkaza oladi. Yechim: nginx `limit_req` va ishlatilmagan
  mijozlarni tozalash.
- **Shaxsiy ma'lumot.** Endi email va so'rovlar bitta foydalanuvchiga bog'lanadi. So'rov matni
  ham shaxsiy ma'lumot bo'lishi mumkin ("ajrashmoqchiman, bolam …"). Qaror (2026-11-06):
  `args` 12 oy saqlanadi, keyin o'chiriladi (son va vaqt qoladi). Bu `/maxfiylik`da yoziladi,
  o'chirish esa kunlik tozalashga qo'shiladi.
- **Google "Testing" holati** — refresh 7 kunda o'ladi va faqat ro'yxatdagi email'lar kira
  oladi. Ochishdan oldin "Production"ga o'tkazish shart.
