"""Sign-in with Google (OpenID Connect, authorization code flow with PKCE).

The ID token comes straight from Google's token endpoint over TLS, so per OpenID Connect Core
3.1.3.7 its signature need not be checked; the claims (issuer, audience, expiry, nonce,
verified e-mail) still are. That keeps us free of JWKS fetching and crypto libraries.
"""

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")
SCOPES = "openid email profile"


class GoogleError(Exception):
    """Sign-in failed; the message is safe to log, not meant for users."""


@dataclass(frozen=True)
class GoogleConfig:
    client_id: str
    client_secret: str


@dataclass(frozen=True)
class GoogleUser:
    subject: str
    email: str
    name: str | None


def start(config: GoogleConfig, redirect_uri: str, state: str) -> tuple[str, dict]:
    """Authorization URL and the state to keep until the callback (``verifier``, ``nonce``)."""
    verifier = secrets.token_urlsafe(48)
    nonce = secrets.token_urlsafe(16)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    query = {
        "client_id": config.client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge.rstrip(b"=").decode(),
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    return f"{AUTH_URL}?{urlencode(query)}", {"verifier": verifier, "nonce": nonce}


def _b64decode(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def parse_id_token(id_token: str, client_id: str, nonce: str, now: float | None = None) -> dict:
    """Claims of an ID token received directly from Google, after checking them."""
    try:
        claims = json.loads(_b64decode(id_token.split(".")[1]))
    except (IndexError, ValueError) as exc:
        raise GoogleError("malformed id_token") from exc
    now = time.time() if now is None else now
    if claims.get("iss") not in ISSUERS:
        raise GoogleError(f"unexpected issuer {claims.get('iss')!r}")
    aud = claims.get("aud")
    if aud != client_id and not (isinstance(aud, list) and client_id in aud):
        raise GoogleError("id_token is for another client")
    if float(claims.get("exp", 0)) < now - 60:
        raise GoogleError("id_token expired")
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise GoogleError("nonce mismatch")
    if not claims.get("sub"):
        raise GoogleError("no subject")
    if not claims.get("email") or claims.get("email_verified") is not True:
        raise GoogleError("e-mail is missing or not verified")
    return claims


async def finish(
    config: GoogleConfig,
    redirect_uri: str,
    code: str,
    login: dict,
    http: httpx.AsyncClient,
) -> GoogleUser:
    """Exchange the callback code and return who signed in."""
    response = await http.post(
        TOKEN_URL,
        data={
            "code": code,
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": login["verifier"],
        },
        timeout=15,
    )
    if response.status_code != 200:
        raise GoogleError(f"token endpoint answered {response.status_code}: {response.text[:200]}")
    id_token = response.json().get("id_token")
    if not id_token:
        raise GoogleError("no id_token in the token response")
    claims = parse_id_token(id_token, config.client_id, login["nonce"])
    return GoogleUser(subject=claims["sub"], email=claims["email"], name=claims.get("name"))
