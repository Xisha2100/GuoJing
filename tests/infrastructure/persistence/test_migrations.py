"""Deployment-level checks for Alembic's database history."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_migration_builds_and_removes_the_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "migrated.db"
    monkeypatch.setenv("GUOJING_DATABASE_URL", f"sqlite:///{database_path}")
    config = Config("alembic.ini")

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    tables = set(inspect(engine).get_table_names())
    assert {
        "alembic_version",
        "tutorials",
        "tutorial_revisions",
        "tutorial_publications",
        "tutorial_draft_workspaces",
        "admin_users",
        "admin_sessions",
        "admin_login_attempts",
        "admin_audit_events",
        "help_request_results",
    } <= tables
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one() == "wal"

    command.downgrade(config, "base")

    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    engine.dispose()
