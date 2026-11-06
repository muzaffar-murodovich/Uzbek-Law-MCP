from urllib.parse import parse_qs, urlparse

import anyio
import pytest
from mcp.server.auth.provider import AuthorizationParams, RegistrationError, TokenError
from mcp.shared.auth import OAuthClientInformationFull

from qonunshunos.auth import users
from qonunshunos.auth.provider import Provider, allowed_redirect_uri, cleanup
from qonunshunos.db import connect

URL = "https://qonunshunos.example"


def test_allowed_redirect_uris():
    assert allowed_redirect_uri("https://claude.ai/api/mcp/auth_callback")
    assert allowed_redirect_uri("http://localhost:33418/callback")
    assert allowed_redirect_uri("http://127.0.0.1:9000/cb")
    assert not allowed_redirect_uri("http://evil.example/cb")
    assert not allowed_redirect_uri("myapp://cb")
    assert not allowed_redirect_uri("https://claude.ai/cb#frag")


def _client(redirect="https://claude.ai/api/mcp/auth_callback", client_id="client-1"):
    return OAuthClientInformationFull(
        client_id=client_id,
        client_secret="s3cret",
        client_name="Claude",
        redirect_uris=[redirect],
        token_endpoint_auth_method="client_secret_post",
    )


def _params(**kw):
    base = {
        "state": "st",
        "scopes": ["qonunshunos"],
        "code_challenge": "x" * 43,
        "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
        "redirect_uri_provided_explicitly": True,
        "resource": f"{URL}/mcp",
    }
    return AuthorizationParams.model_validate({**base, **kw})


@pytest.fixture
def provider(db_dsn):
    return Provider(lambda: connect(db_dsn), URL)


@pytest.fixture
def user(db_dsn):
    with connect(db_dsn) as conn:
        return users.sign_in(conn, "google", "sub-1", email="a@example.com", name="Ali")


def _code_from(redirect: str) -> str:
    query = parse_qs(urlparse(redirect).query)
    assert query["state"] == ["st"] and query["iss"] == [URL]
    return query["code"][0]


@pytest.mark.db
def test_register_rejects_foreign_http_redirects(provider):
    with pytest.raises(RegistrationError):
        anyio.run(provider.register_client, _client("http://evil.example/cb"))
    anyio.run(provider.register_client, _client())
    loaded = anyio.run(provider.get_client, "client-1")
    assert loaded.client_secret == "s3cret" and loaded.client_name == "Claude"
    assert anyio.run(provider.get_client, "nope") is None


@pytest.mark.db
def test_full_code_and_refresh_flow(provider, user):
    client = _client()
    anyio.run(provider.register_client, client)

    login = anyio.run(provider.authorize, client, _params())
    assert login.startswith(f"{URL}/auth/login?req=")
    request_id = parse_qs(urlparse(login).query)["req"][0]
    pending = provider.get_request(request_id)
    assert pending.client_label == "Claude" and pending.redirect_host == "claude.ai"
    assert not provider.has_consent(user.id, client.client_id)

    code = _code_from(provider.complete_request(request_id, user.id, consent=True))
    assert provider.has_consent(user.id, client.client_id)
    with pytest.raises(LookupError):  # the request is single-use
        provider.complete_request(request_id, user.id)

    loaded = anyio.run(provider.load_authorization_code, client, code)
    assert loaded.subject == str(user.id) and loaded.resource == f"{URL}/mcp"
    assert anyio.run(provider.load_authorization_code, _client(client_id="other"), code) is None

    tokens = anyio.run(provider.exchange_authorization_code, client, loaded)
    assert tokens.expires_in == 3600 and tokens.scope == "qonunshunos"
    with pytest.raises(TokenError):  # codes are single-use
        anyio.run(provider.exchange_authorization_code, client, loaded)

    access = anyio.run(provider.load_access_token, tokens.access_token)
    assert access.subject == str(user.id) and access.resource == f"{URL}/mcp"
    assert anyio.run(provider.load_access_token, "qs_at_bogus") is None

    refresh = anyio.run(provider.load_refresh_token, client, tokens.refresh_token)
    fresh = anyio.run(provider.exchange_refresh_token, client, refresh, [])
    assert fresh.access_token != tokens.access_token
    with pytest.raises(TokenError):  # rotated: the old refresh token is spent
        anyio.run(provider.exchange_refresh_token, client, refresh, [])
    assert anyio.run(provider.load_refresh_token, client, tokens.refresh_token) is None

    # Revoking one token logs this client out completely.
    new_access = anyio.run(provider.load_access_token, fresh.access_token)
    anyio.run(provider.revoke_token, new_access)
    assert anyio.run(provider.load_access_token, fresh.access_token) is None
    assert anyio.run(provider.load_refresh_token, client, fresh.refresh_token) is None


@pytest.mark.db
def test_blocked_user_tokens_stop_working(provider, user, db_dsn):
    client = _client()
    anyio.run(provider.register_client, client)
    request_id = provider.create_request(client, _params())
    code = _code_from(provider.complete_request(request_id, user.id))
    loaded = anyio.run(provider.load_authorization_code, client, code)
    tokens = anyio.run(provider.exchange_authorization_code, client, loaded)
    with connect(db_dsn) as conn:
        conn.execute("UPDATE users SET blocked_at = now() WHERE id = %s", (user.id,))
    assert anyio.run(provider.load_access_token, tokens.access_token) is None


@pytest.mark.db
def test_deny_redirects_with_access_denied(provider):
    client = _client()
    anyio.run(provider.register_client, client)
    request_id = provider.create_request(client, _params())
    query = parse_qs(urlparse(provider.deny_request(request_id)).query)
    assert query["error"] == ["access_denied"] and query["state"] == ["st"]
    assert provider.get_request(request_id) is None


@pytest.mark.db
def test_cleanup_removes_stale_rows(provider, db_dsn):
    anyio.run(provider.register_client, _client())
    with connect(db_dsn) as conn:
        conn.execute("UPDATE oauth_clients SET created_at = now() - interval '2 days'")
        conn.execute(
            "INSERT INTO usage_events (tool, ts, latency_ms, ok, args)"
            " VALUES ('search_law', now() - interval '400 days', 1, true, '{\"query\": \"x\"}')"
        )
        counts = cleanup(conn)
        assert counts["oauth_clients"] == 1 and counts["usage_events.args"] == 1
        assert conn.execute("SELECT args FROM usage_events").fetchone()[0] == {}
