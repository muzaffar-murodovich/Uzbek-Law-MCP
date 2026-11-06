"""Users and their sign-in identities (Google now; other providers later)."""

from dataclasses import dataclass
from datetime import datetime

import psycopg
from psycopg.rows import class_row
from psycopg.types.json import Jsonb

from qonunshunos.auth.limits import Limits, limits_for


@dataclass
class User:
    id: int
    display_name: str | None
    email: str | None
    plan: str
    limits_override: dict
    created_at: datetime
    last_seen_at: datetime | None
    blocked_at: datetime | None
    blocked_reason: str | None

    @property
    def blocked(self) -> bool:
        return self.blocked_at is not None

    @property
    def limits(self) -> Limits:
        return limits_for(self.plan, self.limits_override)


_COLUMNS = (
    "id, display_name, email, plan, limits_override, created_at, last_seen_at, blocked_at,"
    " blocked_reason"
)


def get(conn: psycopg.Connection, user_id: int) -> User | None:
    with conn.cursor(row_factory=class_row(User)) as cur:
        return cur.execute(f"SELECT {_COLUMNS} FROM users WHERE id = %s", (user_id,)).fetchone()


def find(conn: psycopg.Connection, ref: str) -> User | None:
    """User by numeric id or e-mail (case-insensitive)."""
    if ref.isdigit():
        return get(conn, int(ref))
    with conn.cursor(row_factory=class_row(User)) as cur:
        return cur.execute(
            f"SELECT {_COLUMNS} FROM users WHERE lower(email) = lower(%s) ORDER BY id LIMIT 1",
            (ref,),
        ).fetchone()


def sign_in(
    conn: psycopg.Connection,
    provider: str,
    subject: str,
    *,
    email: str | None = None,
    name: str | None = None,
    username: str | None = None,
) -> User:
    """Find the user of this identity or create one; refresh profile data from the provider."""
    with conn.transaction():
        row = conn.execute(
            "SELECT user_id FROM user_identities WHERE provider = %s AND subject = %s FOR UPDATE",
            (provider, subject),
        ).fetchone()
        if row is None:
            (user_id,) = conn.execute(
                "INSERT INTO users (display_name, email) VALUES (%s, %s) RETURNING id",
                (name, email),
            ).fetchone()
            conn.execute(
                "INSERT INTO user_identities (user_id, provider, subject, email, username)"
                " VALUES (%s, %s, %s, %s, %s)",
                (user_id, provider, subject, email, username),
            )
        else:
            (user_id,) = row
            conn.execute(
                "UPDATE user_identities SET email = %s, username = %s"
                " WHERE provider = %s AND subject = %s",
                (email, username, provider, subject),
            )
            conn.execute(
                "UPDATE users SET display_name = coalesce(%s, display_name),"
                " email = coalesce(%s, email) WHERE id = %s",
                (name, email, user_id),
            )
        conn.execute("UPDATE users SET last_seen_at = now() WHERE id = %s", (user_id,))
    return get(conn, user_id)


def set_limits(conn: psycopg.Connection, user_id: int, changes: dict) -> User | None:
    """Merge limit overrides; a ``None`` value removes that override."""
    user = get(conn, user_id)
    if user is None:
        return None
    merged = {**user.limits_override, **changes}
    merged = {k: v for k, v in merged.items() if v is not None}
    conn.execute("UPDATE users SET limits_override = %s WHERE id = %s", (Jsonb(merged), user_id))
    return get(conn, user_id)


def set_plan(conn: psycopg.Connection, user_id: int, plan: str) -> None:
    conn.execute("UPDATE users SET plan = %s WHERE id = %s", (plan, user_id))


def block(conn: psycopg.Connection, user_id: int, reason: str | None = None) -> None:
    """Block the user and revoke all their tokens at once."""
    with conn.transaction():
        conn.execute(
            "UPDATE users SET blocked_at = now(), blocked_reason = %s WHERE id = %s",
            (reason, user_id),
        )
        conn.execute(
            "UPDATE oauth_tokens SET revoked_at = now() WHERE user_id = %s AND revoked_at IS NULL",
            (user_id,),
        )


def unblock(conn: psycopg.Connection, user_id: int) -> None:
    conn.execute(
        "UPDATE users SET blocked_at = NULL, blocked_reason = NULL WHERE id = %s", (user_id,)
    )


def overview(conn: psycopg.Connection, since: datetime, limit: int = 50) -> list[tuple]:
    """``(user, identities, calls since, searches since)`` rows, most recently seen first."""
    rows = conn.execute(
        """
        SELECT u.id,
               coalesce(string_agg(DISTINCT i.provider, ','), '') AS providers,
               (SELECT count(*) FROM usage_events e
                 WHERE e.user_id = u.id AND e.ts >= %(since)s AND e.counted) AS calls,
               (SELECT count(*) FROM usage_events e
                 WHERE e.user_id = u.id AND e.ts >= %(since)s AND e.counted
                   AND e.tool = 'search_law') AS searches
        FROM users u LEFT JOIN user_identities i ON i.user_id = u.id
        GROUP BY u.id
        ORDER BY u.last_seen_at DESC NULLS LAST, u.id DESC
        LIMIT %(limit)s
        """,
        {"since": since, "limit": limit},
    ).fetchall()
    return [
        (get(conn, uid), providers, calls, searches) for uid, providers, calls, searches in rows
    ]
