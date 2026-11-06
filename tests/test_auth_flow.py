"""End-to-end OAuth: the SDK's OAuth client registers, signs in (dev login), consents, gets a
token and calls tools over Streamable HTTP; limits apply per user. Needs QONUNSHUNOS_TEST_DSN."""

import re
from urllib.parse import parse_qs, urljoin, urlparse

import anyio
import httpx2
import pytest
from fakes import FakeEmbedder
from mcp import Client
from mcp.client.auth import OAuthClientProvider
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import AuthorizationCodeResult, OAuthClientMetadata, OAuthToken

from qonunshunos.auth import users
from qonunshunos.auth.pages import AuthConfig
from qonunshunos.db import connect
from qonunshunos.mcp.server import Services, create_server

pytestmark = pytest.mark.db

BASE = "http://localhost:8000"
CALLBACK = "http://localhost:3030/callback"


class MemoryStorage:
    def __init__(self):
        self.tokens = None
        self.client = None

    async def get_tokens(self):
        return self.tokens

    async def set_tokens(self, tokens: OAuthToken):
        self.tokens = tokens

    async def get_client_info(self):
        return self.client

    async def set_client_info(self, client_info):
        self.client = client_info


class Browser:
    """Plays the user: follows the authorization URL through sign-in and consent."""

    def __init__(self, app, *, consent: bool = True):
        self.http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url=BASE)
        self.consent = consent
        self.result: AuthorizationCodeResult | None = None
        self.pages: list[str] = []

    async def redirect(self, url: str) -> None:
        response = await self.http.get(url)  # SDK /authorize → our login page
        assert response.status_code == 302, response.text
        response = await self.http.get(response.headers["location"])
        self.pages.append(response.text)
        assert "Qonunshunos'ga kirish" in response.text and "Test foydalanuvchi" in response.text
        request_id = re.search(r"name='req' value='([^']+)'", response.text).group(1)
        response = await self.http.post("/auth/dev", data={"req": request_id})
        if response.status_code == 200:  # first time for this client: consent page
            self.pages.append(response.text)
            token = re.search(r"name='token' value='([^']+)'", response.text).group(1)
            decision = "allow" if self.consent else "deny"
            response = await self.http.post(
                "/auth/consent", data={"req": request_id, "token": token, "decision": decision}
            )
        assert response.status_code == 302
        target = urljoin(BASE, response.headers["location"])
        assert target.startswith(CALLBACK)
        query = parse_qs(urlparse(target).query)
        if "error" in query:
            raise PermissionError(query["error"][0])
        self.result = AuthorizationCodeResult(
            code=query["code"][0], state=query["state"][0], iss=query.get("iss", [None])[0]
        )

    async def callback(self) -> AuthorizationCodeResult:
        return self.result


@pytest.fixture
def app(db_dsn):
    services = Services(db_dsn, None, embedder=FakeEmbedder())
    server = create_server(services, AuthConfig(public_url=BASE, dev_login=True))
    return server.streamable_http_app(stateless_http=True, json_response=True)


def _oauth(browser: Browser, storage: MemoryStorage) -> OAuthClientProvider:
    return OAuthClientProvider(
        server_url=f"{BASE}/mcp",
        client_metadata=OAuthClientMetadata(
            client_name="Test client",
            redirect_uris=[CALLBACK],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
        ),
        storage=storage,
        redirect_handler=browser.redirect,
        callback_handler=browser.callback,
    )


async def _call(app, oauth, tool: str, args: dict | None = None) -> str:
    http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), auth=oauth, timeout=10)
    async with http, Client(streamable_http_client(f"{BASE}/mcp", http_client=http)) as client:
        result = await client.call_tool(tool, args or {})
        assert not result.is_error, result
        return result.content[0].text


def test_metadata_and_unauthenticated_request(app):
    async def scenario():
        async with app.router.lifespan_context(app):
            http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url=BASE)
            async with http:
                response = await http.post("/mcp", json={})
                assert response.status_code == 401
                assert "resource_metadata=" in response.headers["www-authenticate"]
                prm = (await http.get("/.well-known/oauth-protected-resource/mcp")).json()
                assert prm["resource"] == f"{BASE}/mcp"
                meta = (await http.get("/.well-known/oauth-authorization-server")).json()
                assert meta["registration_endpoint"] == f"{BASE}/register"
                assert meta["code_challenge_methods_supported"] == ["S256"]
                assert "Kirish havolasi eskirgan" in (await http.get("/auth/login?req=x")).text

    anyio.run(scenario)


def test_sign_in_call_tools_and_limits(app, db_dsn):
    browser = Browser(app)
    storage = MemoryStorage()

    async def scenario():
        async with app.router.lifespan_context(app):
            oauth = _oauth(browser, storage)
            text = await _call(app, oauth, "find_document", {"query": "Mehnat kodeksi"})
            assert "Mehnat kodeksi" in text  # the empty test database finds nothing, says so
            assert any("Ruxsat berasizmi?" in p and "localhost" in p for p in browser.pages)
            assert storage.tokens.access_token.startswith("qs_at_")

            # A second connection reuses the stored token: no new sign-in.
            pages_before = len(browser.pages)
            await _call(app, oauth, "list_codes")
            assert len(browser.pages) == pages_before

            with connect(db_dsn) as conn:
                user = users.find(conn, "test@localhost")
                users.set_limits(conn, user.id, {"other": 1})
            refused = await _call(app, oauth, "find_document", {"query": "Mehnat"})
            assert "Bugungi bepul limit tugadi" in refused
            assert "kuniga 1 ta boshqa soʻrov" in refused

    anyio.run(scenario)
    with connect(db_dsn) as conn:
        rows = conn.execute(
            "SELECT tool, counted, user_id IS NOT NULL FROM usage_events ORDER BY id"
        ).fetchall()
    assert rows == [
        ("find_document", True, True),
        ("list_codes", True, True),
        ("find_document", False, True),
    ]


def test_denied_consent_gives_no_token(app):
    browser = Browser(app, consent=False)
    storage = MemoryStorage()

    async def scenario():
        async with app.router.lifespan_context(app):
            with pytest.raises(Exception):  # noqa: B017 (the SDK wraps the denial)
                await _call(app, _oauth(browser, storage), "list_codes")
            assert storage.tokens is None

    anyio.run(scenario)
