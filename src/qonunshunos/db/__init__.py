"""PostgreSQL access: connections and SQL-file migrations."""

import logging
from importlib import resources

import psycopg
from pgvector.psycopg import register_vector

log = logging.getLogger(__name__)


def connect(dsn: str, *, vector: bool = True) -> psycopg.Connection:
    """Autocommit connection: multi-statement writes use explicit ``conn.transaction()``."""
    if not dsn:
        raise ValueError("database DSN is empty: set QONUNSHUNOS_DSN (see .env.example)")
    conn = psycopg.connect(dsn, autocommit=True)
    if vector:
        register_vector(conn)
    return conn


def migration_files() -> list[tuple[str, str]]:
    """``(version, sql)`` pairs sorted by file name (``0001_init.sql`` → ``0001``)."""
    folder = resources.files("qonunshunos.db") / "migrations"
    files = sorted(f for f in folder.iterdir() if f.name.endswith(".sql"))
    return [(f.name.split("_", 1)[0], f.read_text(encoding="utf-8")) for f in files]


def migrate(dsn: str) -> list[str]:
    """Apply pending migrations, each in its own transaction. Returns applied versions."""
    applied = []
    with connect(dsn, vector=False) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        done = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
        for version, sql in migration_files():
            if version in done:
                continue
            with conn.transaction():
                conn.execute(sql)
                conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
            log.info("applied migration %s", version)
            applied.append(version)
    return applied
