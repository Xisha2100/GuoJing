"""Deployment-level checks for Alembic's database history."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_migration_replaces_legacy_schema_with_agent_tables(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "migrated.db"
    monkeypatch.setenv("GUOJING_DATABASE_URL", f"sqlite:///{database_path}")
    config = Config("alembic.ini")

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    tables = set(inspect(engine).get_table_names())
    assert tables == {
        "agent_runs",
        "agent_sessions",
        "alembic_version",
        "guidance_steps",
    }
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one() == "wal"
    persisted_columns = {
        column["name"]
        for table in tables - {"alembic_version"}
        for column in inspect(engine).get_columns(table)
    }
    assert (
        not {
            "screenshot",
            "screenshot_base64",
            "model_messages",
            "internal_reasoning",
            "tool_output",
        }
        & persisted_columns
    )

    engine.dispose()
