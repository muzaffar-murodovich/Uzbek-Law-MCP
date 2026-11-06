import base64
import json
import time
from urllib.parse import parse_qs, urlparse

import anyio
import httpx
import httpx2
import pytest
from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull

from qonunshunos.auth import google
from qonunshunos.auth.google import GoogleConfig, GoogleError
from qonunshunos.auth.pages import AuthConfig, routes
from qonunshunos.auth.provider import Provider
from qonunshunos.db import connect

CONFIG = GoogleConfig(client_id="cid.apps.googleusercontent.com", client_secret="gsecret")


def _id_token(**claims) -> str:
    base = {
        "iss": "https://accounts.google.com",
        "aud": CONFIG.client_id,
        "sub": "1234567890",
        "email": "ali@gmail.com",
        "email_verified": True,
        "name": "Ali Valiyev",
        "nonce": "n1",
        "exp": time.time() + 3600,
    }
    payload = base64.urlsafe_b64encode(json.dumps({**base, **claims}).encode()).rstrip(b"=")
    return f"eyJhbGciOiJSUzI1NiJ9.{payload.decode()}.sig"


def test_start_url_has_pkce_state_and_nonce():
    url, login = google.start(CONFIG, "https://q.example/auth/google/callback", "req-1")
    query = parse_qs(urlparse(url).query)
    assert query["state"] == ["req-1"] and query["nonce"] == [login["nonce"]]
    assert query["scope"] == ["openid email profile"]
    assert query["code_challenge_method"] == ["S256"] and len(login["verifier"]) >= 43


def test_parse_id_token_checks_claims():
    claims = google.parse_id_token(_id_token(), CONFIG.client_id, "n1")
    assert claims["sub"] == "1234567890"
    for bad in (
        {"iss": "https://evil.example"},
        {"aud": "other-client"},
        {"exp": time.time() - 3600},
        {"nonce": "n2"},
        {"email_verified": False},
        {"sub": ""},
    ):
        with pytest.raises(GoogleError):
            google.parse_id_token(_id_token(**bad), CONFIG.client_id, "n1")
    with pytest.raises(GoogleError):
        google.parse_id_token("not-a-jwt", CONFIG.client_id, "n1")


def _google_mock(seen: list, nonce=lambda: "n1") -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(parse_qs(request.content.decode()))
        token = _id_token(nonce=nonce())
        return httpx.Response(200, json={"id_token": token, "access_token": "ya29"})

    return httpx.MockTransport(handler)


def test_finish_exchanges_code():
    seen = []

    async def scenario():
        async with httpx.AsyncClient(transport=_google_mock(seen)) as http:
            login = {"verifier": "v" * 50, "nonce": "n1"}
            return await google.finish(CONFIG, "https://q/cb", "code-1", login, http)

    who = anyio.run(scenario)
    assert who.subject == "1234567890" and who.email == "ali@gmail.com"
    assert seen[0]["code_verifier"] == ["v" * 50] and seen[0]["code"] == ["code-1"]


@pytest.mark.db
def test_google_callback_signs_in_and_shows_consent(db_dsn):
    from mcp.server.mcpserver import MCPServer

    seen = []
    base = "https://q.example"
    config = AuthConfig(public_url=base, google=CONFIG)
    provider = Provider(lambda: connect(db_dsn), base)
    server = MCPServer("t")
    request_id = None

    def stored_nonce():  # the fake Google echoes the nonce we sent, as the real one does
        return provider.get_login(request_id)["nonce"]

    def factory():
        return httpx.AsyncClient(transport=_google_mock(seen, stored_nonce))

    for path, methods, handler in routes(provider, config, lambda: connect(db_dsn), factory):
        server.custom_route(path, methods=methods)(handler)
    app = server.streamable_http_app()

    client = OAuthClientInformationFull(
        client_id="c1", client_name="Claude", redirect_uris=["https://claude.ai/cb"]
    )
    anyio.run(provider.register_client, client)
    params = AuthorizationParams(
        state="st",
        scopes=None,
        code_challenge="c" * 43,
        redirect_uri="https://claude.ai/cb",
        redirect_uri_provided_explicitly=True,
    )
    request_id = provider.create_request(client, params)

    async def scenario():
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(transport=transport, base_url=base) as browser:
            page = await browser.get(f"/auth/login?req={request_id}")
            assert "Google orqali kirish" in page.text and "Test foydalanuvchi" not in page.text
            start = await browser.get(f"/auth/google/start?req={request_id}")
            assert start.headers["location"].startswith(google.AUTH_URL)
            # Same flow from another browser (no cookie) is refused.
            async with httpx2.AsyncClient(transport=transport, base_url=base) as other:
                stranger = await other.get(f"/auth/google/callback?state={request_id}&code=c")
                assert "boshqa brauzerda" in stranger.text
            done = await browser.get(f"/auth/google/callback?state={request_id}&code=gcode")
            assert done.status_code == 200 and "Ruxsat berasizmi?" in done.text
            assert "ali@gmail.com" in done.text and "claude.ai" in done.text

    anyio.run(scenario)
    assert seen[0]["redirect_uri"] == [f"{base}/auth/google/callback"]
    pending = provider.get_request(request_id)
    assert pending.params.resource == f"{base}/mcp"  # filled in for clients without RFC 8707
    with connect(db_dsn) as conn:
        row = conn.execute(
            "SELECT u.email, u.display_name FROM users u JOIN user_identities i ON i.user_id = u.id"
            " WHERE i.provider = 'google' AND i.subject = '1234567890'"
        ).fetchone()
    assert row == ("ali@gmail.com", "Ali Valiyev")
