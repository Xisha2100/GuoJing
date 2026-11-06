"""SQLAlchemy engine and transaction-session configuration."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from guojing.domain.device_access import AccessDenied


class Database:
    """Own one engine and create one short-lived Session per transaction."""

    def __init__(self, database_url: str) -> None:
        ensure_sqlite_parent_exists(database_url)
        self.engine = create_engine(database_url, hide_parameters=True)
        if self.engine.dialect.name == "sqlite":
            event.listen(self.engine, "connect", _configure_sqlite_connection)
        self._session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
        )

    @contextmanager
    def new_session(self) -> Iterator[Session]:
        """Create a session; callers must close it, normally via a context manager."""
        try:
            with self._session_factory() as session:
                yield session
        except OperationalError as error:
            if isinstance(error.orig, sqlite3.OperationalError) and getattr(
                error.orig, "sqlite_errorcode", None
            ) in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
                raise AccessDenied("service_busy", 503, 5) from None
            raise

    def dispose(self) -> None:
        """Release pooled database connections during application shutdown."""
        self.engine.dispose()


def ensure_sqlite_parent_exists(database_url: str) -> None:
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite") or not url.database:
        return
    if url.database == ":memory:" or url.database.startswith("file:"):
        return
    Path(url.database).expanduser().parent.mkdir(parents=True, exist_ok=True)


def _configure_sqlite_connection(
    dbapi_connection: Any,
    _connection_record: Any,
) -> None:
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA secure_delete=ON")
    cursor.close()


def enable_sqlite_wal(engine: Engine) -> None:
    """Enable WAL explicitly during database migration/bootstrap."""
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
