"""
Phase 6 regression tests:
- SQLite PRAGMA hook only fires for sqlite connections (never PostgreSQL psycopg2 connections)
- SQLAlchemy engine options include pool_pre_ping/pool_recycle on PostgreSQL DATABASE_URL
- Migration DDL adapts AUTOINCREMENT -> SERIAL PRIMARY KEY for postgresql and uses BOOLEAN DEFAULT FALSE
- .dockerignore excludes runtime dev DBs, uploads, and logs
"""

from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import inspect

from app import create_app
from core.migrations import MIGRATIONS, _adapt_sql_for_dialect, run_migrations
from core.models import db, set_sqlite_pragma


class FakePostgresConnection:
    __module__ = "psycopg2.extensions"

    def __init__(self, log_list):
        self._log = log_list

    def cursor(self):
        return self

    def execute(self, sql):
        self._log.append(sql)

    def close(self):
        pass


def test_sqlite_pragma_skips_non_sqlite_connections():
    executed = []
    set_sqlite_pragma(FakePostgresConnection(executed), None)
    assert executed == [], f"SQLite PRAGMAs must not run on Postgres: {executed}"

    class FakeSqliteConn:
        __module__ = "sqlite3"

        def cursor(self):
            return self

        def execute(self, sql):
            executed.append(sql)

        def close(self):
            pass

    set_sqlite_pragma(FakeSqliteConn(), None)
    assert any("PRAGMA journal_mode=WAL" in s for s in executed)


def test_migration_ddl_adapts_for_postgresql():
    for version, _desc, sql in MIGRATIONS:
        if not sql:
            continue
        assert "BOOLEAN DEFAULT 0" not in sql, f"Migration {version} uses non-portable BOOLEAN DEFAULT 0"
        pg_sql = _adapt_sql_for_dialect(sql, "postgresql")
        assert "AUTOINCREMENT" not in pg_sql, f"Migration {version} still contains AUTOINCREMENT for postgres"


def test_dockerignore_excludes_local_runtime_data():
    content = Path(".dockerignore").read_text(encoding="utf-8")
    for pattern in ("instance/", "*.db", "uploads/*", "logs/"):
        assert pattern in content, f".dockerignore missing {pattern}"


def test_postgres_engine_options_configured_for_non_sqlite(monkeypatch):
    # Ensure engine options logic prepares pool_pre_ping when non-sqlite URI is present without connecting live
    uri = "postgresql+psycopg2://user:pass@localhost:5432/medimind"
    monkeypatch.setenv("DATABASE_URL", uri)
    # Inspect create_app config branch directly without running init_db live connection
    from app import Flask
    import app as app_mod

    with monkeypatch.context() as m:
        m.setattr(app_mod, "init_db", lambda a: None)
        app_inst = create_app({"TESTING": True})
        assert app_inst.config["SQLALCHEMY_ENGINE_OPTIONS"]["pool_pre_ping"] is True
        assert app_inst.config["SQLALCHEMY_ENGINE_OPTIONS"]["pool_recycle"] == 300
