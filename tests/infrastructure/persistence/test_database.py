"""Database connection safety defaults."""

from pathlib import Path

from guojing.infrastructure.persistence.database import Database


def test_sqlite_application_connections_enforce_integrity_settings(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'settings.db'}")

    with database.engine.connect() as connection:
        foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()
        busy_timeout = connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one()

    assert foreign_keys == 1
    assert busy_timeout == 5000
    database.dispose()
