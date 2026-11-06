"""Sign-in and consent pages (/auth/*) between the SDK's /authorize and the client redirect.

Flow: /authorize (SDK) → provider.authorize → /auth/login → Google (or dev login) → user found →
consent page unless this client was already approved → code → client redirect_uri.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from html import escape
from string import Template

import anyio
import httpx
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from qonunshunos.auth import google, users
from qonunshunos.auth.google import GoogleConfig
from qonunshunos.auth.provider import PendingRequest, Provider

log = logging.getLogger(__name__)

REQUEST_COOKIE = "qs_req"


@dataclass(frozen=True)
class AuthConfig:
    public_url: str
    google: GoogleConfig | None = None
    dev_login: bool = False  # "sign in as a test user" button, local development only

    @property
    def google_redirect_uri(self) -> str:
        return f"{self.public_url.rstrip('/')}/auth/google/callback"

    @property
    def secure_cookies(self) -> bool:
        return self.public_url.startswith("https://")


PAGE = Template("""<!doctype html>
<html lang="uz">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title — Qonunshunos</title>
<style>
:root { --bg: #f6f5f2; --card: #fff; --text: #1d1d1b; --muted: #66645e; --line: #dedbd3;
  --accent: #1f5f8b; --accent-text: #fff; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #161615; --card: #20201e; --text: #ecebe6; --muted: #a3a19a; --line: #3a3935;
    --accent: #6aa9d6; --accent-text: #0d1b26; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
  font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 440px; margin: 10vh auto; padding: 0 16px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 12px;
  padding: 28px 24px; }
h1 { font-size: 1.3rem; margin: 0 0 12px; }
p { margin: 0 0 14px; }
.muted { color: var(--muted); font-size: .9rem; }
.button { display: block; width: 100%; padding: 12px 16px; margin: 10px 0 0;
  border-radius: 8px; border: 1px solid var(--line); background: var(--card);
  color: var(--text); font: inherit; text-align: center; text-decoration: none;
  cursor: pointer; }
.primary { background: var(--accent); border-color: var(--accent); color: var(--accent-text); }
form { margin: 0; }
footer { margin-top: 16px; text-align: center; }
a { color: var(--accent); }
</style>
</head>
<body>
<main>
<div class="card">
$body
</div>
<footer class="muted"><a href="/maxfiylik">Maxfiylik siyosati</a> ·
<a href="/shartlar">Foydalanish shartlari</a></footer>
</main>
</body>
</html>
""")


def page(title: str, body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(PAGE.substitute(title=escape(title), body=body), status_code=status)


def error_page(message: str, status: int = 400) -> HTMLResponse:
    body = (
        "<h1>Kirib boʻlmadi</h1>"
        f"<p>{escape(message)}</p>"
        "<p class='muted'>AI ilovangizda (Claude, ChatGPT va hokazo) Qonunshunos konnektorini "
        "qaytadan ulang.</p>"
    )
    return page("Xato", body, status)


EXPIRED = "Kirish havolasi eskirgan yoki allaqachon ishlatilgan."


def _client_line(pending: PendingRequest) -> str:
    return (
        f"<b>{escape(pending.client_label)}</b> "
        f"<span class='muted'>({escape(pending.redirect_host)})</span>"
    )


def login_page(pending: PendingRequest, config: AuthConfig) -> HTMLResponse:
    buttons = []
    if config.google:
        buttons.append(
            f"<a class='button primary' href='/auth/google/start?req={escape(pending.id)}'>"
            "Google orqali kirish</a>"
        )
    if config.dev_login:
        buttons.append(
            "<form method='post' action='/auth/dev'>"
            f"<input type='hidden' name='req' value='{escape(pending.id)}'>"
            "<button class='button'>Test foydalanuvchi sifatida kirish</button></form>"
        )
    body = (
        "<h1>Qonunshunos'ga kirish</h1>"
        f"<p>{_client_line(pending)} Oʻzbekiston qonunchiligidan qidirish uchun "
        "Qonunshunos'ga ulanmoqchi.</p>"
        "<p class='muted'>Xizmat bepul. Kirish faqat kunlik limitlarni hisoblash uchun kerak: "
        "parolingiz bizga kelmaydi, biz faqat ismingiz va emailingizni koʻramiz.</p>"
        + "".join(buttons)
    )
    return page("Kirish", body)


def consent_page(pending: PendingRequest, user: users.User, token: str) -> HTMLResponse:
    who = escape(user.email or user.display_name or f"#{user.id}")
    hidden = (
        f"<input type='hidden' name='req' value='{escape(pending.id)}'>"
        f"<input type='hidden' name='token' value='{escape(token)}'>"
    )
    body = (
        "<h1>Ruxsat berasizmi?</h1>"
        f"<p>{_client_line(pending)} sizning nomingizdan ({who}) Qonunshunos'dan "
        "foydalanmoqchi: qonunlarni qidirish va moddalarni oʻqish.</p>"
        "<p class='muted'>Qavs ichidagi manzilni tekshiring: agar bu ilovani siz ulamagan "
        "boʻlsangiz, rad eting.</p>"
        "<form method='post' action='/auth/consent'>"
        f"{hidden}<button class='button primary' name='decision' value='allow'>Ruxsat berish"
        "</button><button class='button' name='decision' value='deny'>Rad etish</button>"
        "</form>"
    )
    return page("Ruxsat", body)


Route = tuple[str, list[str], Callable[[Request], Awaitable[Response]]]


def routes(provider: Provider, config: AuthConfig, connect, http_factory=None) -> list[Route]:
    """``(path, methods, handler)`` triples for ``MCPServer.custom_route``."""
    http_factory = http_factory or (lambda: httpx.AsyncClient())

    def run(fn, *args):
        return anyio.to_thread.run_sync(fn, *args)

    def sign_in(provider_name: str, subject: str, **profile) -> users.User:
        with connect() as conn:
            return users.sign_in(conn, provider_name, subject, **profile)

    async def signed_in(pending: PendingRequest, user: users.User) -> Response:
        if user.blocked:
            await run(provider.deny_request, pending.id)
            return error_page("Bu akkaunt bloklangan.", 403)
        if await run(provider.has_consent, user.id, pending.client.client_id):
            try:
                target = await run(provider.complete_request, pending.id, user.id)
            except LookupError:
                return error_page(EXPIRED)
            return RedirectResponse(target, status_code=302)
        token = await run(provider.bind_user, pending.id, user.id)
        return consent_page(pending, user, token)

    async def login(request: Request) -> Response:
        pending = await run(provider.get_request, request.query_params.get("req", ""))
        if pending is None:
            return error_page(EXPIRED)
        if not config.google and not config.dev_login:
            return error_page("Kirish usullari sozlanmagan.", 503)
        return login_page(pending, config)

    async def google_start(request: Request) -> Response:
        request_id = request.query_params.get("req", "")
        pending = await run(provider.get_request, request_id)
        if pending is None or config.google is None:
            return error_page(EXPIRED)
        url, login_state = google.start(config.google, config.google_redirect_uri, request_id)
        await run(provider.set_login, request_id, login_state)
        response = RedirectResponse(url, status_code=302)
        # Ties the callback to this browser (login CSRF).
        response.set_cookie(
            REQUEST_COOKIE,
            request_id,
            max_age=600,
            path="/auth",
            httponly=True,
            secure=config.secure_cookies,
            samesite="lax",
        )
        return response

    async def google_callback(request: Request) -> Response:
        request_id = request.query_params.get("state", "")
        pending = await run(provider.get_request, request_id)
        if pending is None or config.google is None:
            return error_page(EXPIRED)
        if request.query_params.get("error"):
            target = await run(provider.deny_request, request_id)
            return RedirectResponse(target, status_code=302) if target else error_page(EXPIRED)
        if request.cookies.get(REQUEST_COOKIE) != request_id:
            return error_page("Kirish boshqa brauzerda boshlangan. Qaytadan urinib koʻring.")
        login_state = await run(provider.get_login, request_id)
        code = request.query_params.get("code")
        if not login_state or not code:
            return error_page(EXPIRED)
        try:
            async with http_factory() as http:
                who = await google.finish(
                    config.google, config.google_redirect_uri, code, login_state, http
                )
        except (google.GoogleError, httpx.HTTPError) as exc:
            log.warning("google sign-in failed: %s", exc)
            return error_page("Google orqali kirishda xato. Qaytadan urinib koʻring.", 502)
        user = await run(lambda: sign_in("google", who.subject, email=who.email, name=who.name))
        response = await signed_in(pending, user)
        response.delete_cookie(REQUEST_COOKIE, path="/auth")
        return response

    async def dev_login(request: Request) -> Response:
        if not config.dev_login:
            return error_page("Topilmadi.", 404)
        form = await request.form()
        pending = await run(provider.get_request, str(form.get("req", "")))
        if pending is None:
            return error_page(EXPIRED)
        user = await run(
            lambda: sign_in("dev", "local", email="test@localhost", name="Test foydalanuvchi")
        )
        return await signed_in(pending, user)

    async def consent(request: Request) -> Response:
        form = await request.form()
        request_id = str(form.get("req", ""))
        user_id = await run(provider.consent_user, request_id, str(form.get("token", "")))
        if user_id is None:
            return error_page(EXPIRED)
        if form.get("decision") != "allow":
            target = await run(provider.deny_request, request_id)
            return RedirectResponse(target, status_code=302) if target else error_page(EXPIRED)
        try:
            target = await run(lambda: provider.complete_request(request_id, user_id, consent=True))
        except LookupError:
            return error_page(EXPIRED)
        return RedirectResponse(target, status_code=302)

    return [
        ("/auth/login", ["GET"], login),
        ("/auth/google/start", ["GET"], google_start),
        ("/auth/google/callback", ["GET"], google_callback),
        ("/auth/dev", ["POST"], dev_login),
        ("/auth/consent", ["POST"], consent),
    ]
