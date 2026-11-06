"""OAuth 2.1 authorization server state in PostgreSQL, behind the MCP SDK's auth routes.

The SDK handles the protocol (metadata, PKCE, redirect and client checks); this module stores
clients, pending authorization requests, codes and tokens. Codes and tokens are random strings
kept as SHA-256 digests, so a database leak does not leak usable tokens.
"""

import hashlib
import secrets
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode, urlparse

import anyio
import psycopg
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from psycopg.types.json import Jsonb

SCOPE = "qonunshunos"
REQUEST_TTL = timedelta(minutes=10)
CODE_TTL = timedelta(minutes=5)
ACCESS_TTL = timedelta(hours=1)
REFRESH_TTL = timedelta(days=60)
UNUSED_CLIENT_TTL = timedelta(days=1)
USAGE_ARGS_TTL = timedelta(days=365)  # privacy policy: query texts are kept 12 months

Connect = Callable[[], AbstractContextManager[psycopg.Connection]]


def digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def allowed_redirect_uri(uri: str) -> bool:
    """HTTPS anywhere, plain HTTP only to the loopback interface (desktop and CLI clients)."""
    parsed = urlparse(uri)
    if parsed.fragment:
        return False
    if parsed.scheme == "https":
        return bool(parsed.hostname)
    return parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1")


@dataclass
class PendingRequest:
    id: str
    client: OAuthClientInformationFull
    params: AuthorizationParams

    @property
    def client_label(self) -> str:
        return self.client.client_name or "Nomaʼlum ilova"

    @property
    def redirect_host(self) -> str:
        return urlparse(str(self.params.redirect_uri)).hostname or ""


class Provider:
    """``OAuthAuthorizationServerProvider`` for the SDK plus helpers for the login pages."""

    def __init__(self, connect: Connect, public_url: str):
        self.connect = connect
        self.public_url = public_url.rstrip("/")
        self.resource_url = f"{self.public_url}/mcp"

    # ---- SDK interface (async, the work runs in a thread) ----

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return await anyio.to_thread.run_sync(self._get_client, client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        bad = [str(u) for u in client_info.redirect_uris or [] if not allowed_redirect_uri(str(u))]
        if bad:
            raise RegistrationError(
                "invalid_redirect_uri", f"only https or loopback http redirect URIs: {bad[0]}"
            )
        await anyio.to_thread.run_sync(self._register_client, client_info)

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        request_id = await anyio.to_thread.run_sync(self.create_request, client, params)
        return f"{self.public_url}/auth/login?{urlencode({'req': request_id})}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        return await anyio.to_thread.run_sync(self._load_code, client, authorization_code)

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        return await anyio.to_thread.run_sync(self._exchange_code, client, authorization_code)

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        return await anyio.to_thread.run_sync(self._load_refresh, client, refresh_token)

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        return await anyio.to_thread.run_sync(self._exchange_refresh, client, refresh_token)

    async def load_access_token(self, token: str) -> AccessToken | None:
        return await anyio.to_thread.run_sync(self._load_access, token)

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        await anyio.to_thread.run_sync(self._revoke, token)

    # ---- clients ----

    def _get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT info FROM oauth_clients WHERE client_id = %s", (client_id,)
            ).fetchone()
        return OAuthClientInformationFull.model_validate(row[0]) if row else None

    def _register_client(self, client_info: OAuthClientInformationFull) -> None:
        info = client_info.model_dump(mode="json", exclude_none=True)
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO oauth_clients (client_id, info) VALUES (%s, %s)",
                (client_info.client_id, Jsonb(info)),
            )

    # ---- pending authorization requests (used by the login pages) ----

    def create_request(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        request_id = secrets.token_urlsafe(24)
        if params.resource is None:  # clients that skip RFC 8707 still get a token for /mcp
            params = params.model_copy(update={"resource": self.resource_url})
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO auth_requests (id, client_id, params, expires_at)"
                " VALUES (%s, %s, %s, now() + %s)",
                (request_id, client.client_id, Jsonb(params.model_dump(mode="json")), REQUEST_TTL),
            )
        return request_id

    def get_request(self, request_id: str) -> PendingRequest | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT r.params, c.info FROM auth_requests r"
                " JOIN oauth_clients c USING (client_id)"
                " WHERE r.id = %s AND r.expires_at > now()",
                (request_id,),
            ).fetchone()
        if row is None:
            return None
        return PendingRequest(
            id=request_id,
            client=OAuthClientInformationFull.model_validate(row[1]),
            params=AuthorizationParams.model_validate(row[0]),
        )

    def set_login(self, request_id: str, login: dict) -> None:
        """Remember upstream sign-in state (e.g. Google PKCE verifier and nonce)."""
        with self.connect() as conn:
            conn.execute(
                "UPDATE auth_requests SET login = %s WHERE id = %s", (Jsonb(login), request_id)
            )

    def get_login(self, request_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT login FROM auth_requests WHERE id = %s AND expires_at > now()",
                (request_id,),
            ).fetchone()
        return row[0] if row else None

    def bind_user(self, request_id: str, user_id: int) -> str:
        """Bind the signed-in user to the request; returns a one-time consent form token."""
        token = secrets.token_urlsafe(24)
        with self.connect() as conn:
            conn.execute(
                "UPDATE auth_requests SET user_id = %s, consent_hash = %s WHERE id = %s",
                (user_id, digest(token), request_id),
            )
        return token

    def consent_user(self, request_id: str, token: str) -> int | None:
        """The user bound to the request, if the consent form token matches."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT user_id FROM auth_requests WHERE id = %s AND consent_hash = %s"
                " AND expires_at > now()",
                (request_id, digest(token)),
            ).fetchone()
        return row[0] if row else None

    def has_consent(self, user_id: int, client_id: str) -> bool:
        with self.connect() as conn:
            return (
                conn.execute(
                    "SELECT 1 FROM oauth_consents WHERE user_id = %s AND client_id = %s",
                    (user_id, client_id),
                ).fetchone()
                is not None
            )

    def complete_request(self, request_id: str, user_id: int, *, consent: bool = False) -> str:
        """Issue an authorization code for a signed-in user; returns the client redirect URL.

        Raises ``LookupError`` when the request is unknown, expired or already used.
        """
        code = secrets.token_urlsafe(32)
        with self.connect() as conn, conn.transaction():
            row = conn.execute(
                "DELETE FROM auth_requests WHERE id = %s AND expires_at > now()"
                " RETURNING client_id, params",
                (request_id,),
            ).fetchone()
            if row is None:
                raise LookupError(request_id)
            client_id, raw = row
            params = AuthorizationParams.model_validate(raw)
            if consent:
                conn.execute(
                    "INSERT INTO oauth_consents (user_id, client_id) VALUES (%s, %s)"
                    " ON CONFLICT DO NOTHING",
                    (user_id, client_id),
                )
            conn.execute(
                "INSERT INTO oauth_codes (code_hash, client_id, user_id, params, expires_at)"
                " VALUES (%s, %s, %s, %s, now() + %s)",
                (digest(code), client_id, user_id, Jsonb(raw), CODE_TTL),
            )
        return construct_redirect_uri(
            str(params.redirect_uri), code=code, state=params.state, iss=self.public_url
        )

    def deny_request(self, request_id: str) -> str | None:
        """Drop the request; returns the client redirect URL carrying ``access_denied``."""
        with self.connect() as conn:
            row = conn.execute(
                "DELETE FROM auth_requests WHERE id = %s RETURNING params", (request_id,)
            ).fetchone()
        if row is None:
            return None
        params = AuthorizationParams.model_validate(row[0])
        return construct_redirect_uri(
            str(params.redirect_uri),
            error="access_denied",
            error_description="Foydalanuvchi ruxsat bermadi",
            state=params.state,
        )

    # ---- codes and tokens ----

    def _load_code(self, client: OAuthClientInformationFull, code: str) -> AuthorizationCode | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT user_id, params, extract(epoch FROM expires_at) FROM oauth_codes"
                " WHERE code_hash = %s AND client_id = %s",
                (digest(code), client.client_id),
            ).fetchone()
        if row is None:
            return None
        user_id, raw, expires_at = row
        params = AuthorizationParams.model_validate(raw)
        return AuthorizationCode(
            code=code,
            scopes=params.scopes or [SCOPE],
            expires_at=float(expires_at),
            client_id=client.client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
            subject=str(user_id),
        )

    def _exchange_code(
        self, client: OAuthClientInformationFull, code: AuthorizationCode
    ) -> OAuthToken:
        with self.connect() as conn, conn.transaction():
            # Codes are single-use: whoever deletes the row first gets the tokens.
            row = conn.execute(
                "DELETE FROM oauth_codes WHERE code_hash = %s AND client_id = %s RETURNING user_id",
                (digest(code.code), client.client_id),
            ).fetchone()
            if row is not None:
                return self._issue(conn, client.client_id, row[0], code.scopes, code.resource)
        # TokenError is a frozen dataclass: raising it through a context manager fails.
        raise TokenError("invalid_grant", "authorization code was already used")

    def _load_refresh(self, client: OAuthClientInformationFull, token: str) -> RefreshToken | None:
        row = self._token_row(digest(token), "refresh")
        if row is None or row["client_id"] != client.client_id:
            return None
        return RefreshToken(
            token=token,
            client_id=client.client_id,
            scopes=row["scopes"],
            expires_at=row["expires_at"],
            resource=row["resource"],
            subject=str(row["user_id"]),
        )

    def _exchange_refresh(
        self, client: OAuthClientInformationFull, token: RefreshToken
    ) -> OAuthToken:
        with self.connect() as conn, conn.transaction():
            # Rotation: the old refresh token works exactly once.
            row = conn.execute(
                "UPDATE oauth_tokens SET revoked_at = now()"
                " WHERE token_hash = %s AND kind = 'refresh' AND revoked_at IS NULL"
                " AND client_id = %s RETURNING user_id",
                (digest(token.token), client.client_id),
            ).fetchone()
            if row is not None:
                return self._issue(conn, client.client_id, row[0], token.scopes, token.resource)
        raise TokenError("invalid_grant", "refresh token was already used")

    def _load_access(self, token: str) -> AccessToken | None:
        row = self._token_row(digest(token), "access")
        if row is None:
            return None
        return AccessToken(
            token=token,
            client_id=row["client_id"],
            scopes=row["scopes"],
            expires_at=row["expires_at"],
            resource=row["resource"],
            subject=str(row["user_id"]),
        )

    def _token_row(self, token_hash: str, kind: str) -> dict | None:
        """A live token of an unblocked user."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT t.client_id, t.user_id, t.scopes, t.resource,"
                " extract(epoch FROM t.expires_at)::bigint"
                " FROM oauth_tokens t JOIN users u ON u.id = t.user_id"
                " WHERE t.token_hash = %s AND t.kind = %s AND t.revoked_at IS NULL"
                " AND t.expires_at > now() AND u.blocked_at IS NULL",
                (token_hash, kind),
            ).fetchone()
        if row is None:
            return None
        keys = ("client_id", "user_id", "scopes", "resource", "expires_at")
        return dict(zip(keys, row, strict=True))

    def _issue(
        self,
        conn: psycopg.Connection,
        client_id: str,
        user_id: int,
        scopes: list[str],
        resource: str | None,
    ) -> OAuthToken:
        access = "qs_at_" + secrets.token_urlsafe(32)
        refresh = "qs_rt_" + secrets.token_urlsafe(32)
        for token, kind, ttl in ((access, "access", ACCESS_TTL), (refresh, "refresh", REFRESH_TTL)):
            conn.execute(
                "INSERT INTO oauth_tokens"
                " (token_hash, kind, client_id, user_id, scopes, resource, expires_at)"
                " VALUES (%s, %s, %s, %s, %s, %s, now() + %s)",
                (digest(token), kind, client_id, user_id, scopes, resource, ttl),
            )
        conn.execute(
            "UPDATE oauth_clients SET last_used_at = now() WHERE client_id = %s", (client_id,)
        )
        conn.execute("UPDATE users SET last_seen_at = now() WHERE id = %s", (user_id,))
        return OAuthToken(
            access_token=access,
            expires_in=int(ACCESS_TTL.total_seconds()),
            scope=" ".join(scopes),
            refresh_token=refresh,
        )

    def _revoke(self, token: AccessToken | RefreshToken) -> None:
        """Revoke every token this client holds for the user (access and refresh alike)."""
        if token.subject is None:
            return
        with self.connect() as conn:
            conn.execute(
                "UPDATE oauth_tokens SET revoked_at = now()"
                " WHERE client_id = %s AND user_id = %s AND revoked_at IS NULL",
                (token.client_id, int(token.subject)),
            )


def cleanup(conn: psycopg.Connection, now: datetime | None = None) -> dict[str, int]:
    """Delete expired requests, codes, tokens and never-used clients; drop old query texts."""
    now = now or datetime.now(UTC)
    counts = {}
    with conn.transaction():
        for table, cond in (
            ("auth_requests", "expires_at < %(now)s"),
            ("oauth_codes", "expires_at < %(now)s"),
            ("oauth_tokens", "expires_at < %(now)s OR revoked_at < %(now)s - interval '1 day'"),
            (
                "oauth_clients",
                "last_used_at IS NULL AND created_at < %(stale)s"
                " AND NOT EXISTS (SELECT 1 FROM auth_requests r"
                "   WHERE r.client_id = oauth_clients.client_id)",
            ),
        ):
            cur = conn.execute(
                f"DELETE FROM {table} WHERE {cond}", {"now": now, "stale": now - UNUSED_CLIENT_TTL}
            )
            counts[table] = cur.rowcount
        cur = conn.execute(
            "UPDATE usage_events SET args = '{}' WHERE ts < %s AND args <> '{}'",
            (now - USAGE_ARGS_TTL,),
        )
        counts["usage_events.args"] = cur.rowcount
    return counts
