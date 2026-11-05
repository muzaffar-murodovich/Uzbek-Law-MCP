import pytest

from qonunshunos.db import connect, migrate, migration_files


def test_migration_files_are_numbered():
    versions = [v for v, _ in migration_files()]
    assert versions[0] == "0001"
    assert versions == sorted(set(versions))


@pytest.mark.db
def test_migrate_is_idempotent(db_dsn):
    assert migrate(db_dsn) == []
    with connect(db_dsn) as conn:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            ).fetchall()
        }
    assert {"documents", "sections", "chunks", "schema_migrations"} <= tables
