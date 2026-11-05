import os
from pathlib import Path

import pytest

from qonunshunos.config import load_dotenv

FIXTURES = Path(__file__).parent / "fixtures" / "lexuz"


@pytest.fixture
def fixture_html():
    def load(name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")

    return load


@pytest.fixture
def db_dsn():
    """DSN of an empty, migrated test database (tests marked ``db``).

    Set ``QONUNSHUNOS_TEST_DSN`` (or put it into ``.env``); the database is wiped. Without it,
    or when the server is down, the test is skipped.
    """
    import psycopg

    from qonunshunos.db import migrate

    load_dotenv(Path(__file__).parent.parent / ".env")
    dsn = os.environ.get("QONUNSHUNOS_TEST_DSN")
    if not dsn:
        pytest.skip("QONUNSHUNOS_TEST_DSN is not set")
    try:
        with psycopg.connect(dsn, connect_timeout=3) as conn:
            conn.execute("DROP SCHEMA public CASCADE")
            conn.execute("CREATE SCHEMA public")
    except psycopg.OperationalError as exc:
        pytest.skip(f"test database is not reachable: {exc}")
    migrate(dsn)
    return dsn
