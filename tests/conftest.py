from pathlib import Path

import pytest

from nizom.config import env, load_dotenv

FIXTURES = Path(__file__).parent / "fixtures" / "lexuz"


@pytest.fixture
def fixture_html():
    def load(name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")

    return load


@pytest.fixture
def db_dsn():
    """DSN of an empty, migrated test database (tests marked ``db``).

    Set ``NIZOM_TEST_DSN`` (or put it into ``.env``); the database is wiped. Without it,
    or when the server is down, the test is skipped.
    """
    import psycopg

    from nizom.db import migrate

    load_dotenv(Path(__file__).parent.parent / ".env")
    dsn = env("TEST_DSN")
    if not dsn:
        pytest.skip("NIZOM_TEST_DSN is not set")
    try:
        with psycopg.connect(dsn, connect_timeout=3) as conn:
            conn.execute("DROP SCHEMA public CASCADE")
            conn.execute("CREATE SCHEMA public")
    except psycopg.OperationalError as exc:
        pytest.skip(f"test database is not reachable: {exc}")
    migrate(dsn)
    return dsn


@pytest.fixture(autouse=True)
def _fresh_chunk_total(monkeypatch):
    """Each test sees its own corpus size, not one cached by an earlier test."""
    from nizom.search import hybrid

    monkeypatch.setattr(hybrid, "_total", None)
