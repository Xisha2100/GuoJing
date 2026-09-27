"""Host process ownership and dependency readiness for the SQLite deployment."""

import fcntl
import shutil
from pathlib import Path
from typing import IO

from sqlalchemy import text
from sqlalchemy.engine import make_url

from guojing.infrastructure.persistence.database import Database

SCHEMA_HEAD = "20260927_13"


class ProcessLease:
    def __init__(self, database_url: str) -> None:
        database = make_url(database_url).database
        if not database or database == ":memory:":
            raise ValueError("a file-backed database is required")
        self.directory = Path(database).expanduser().resolve().parent
        self.path = Path(database).expanduser().resolve().with_suffix(".process.lock")
        self._file: IO[str] | None = None

    def acquire(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        file = self.path.open("a")
        try:
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            file.close()
            raise RuntimeError("another API process already owns this database") from None
        self._file = file

    def release(self) -> None:
        if self._file is not None:
            fcntl.flock(self._file, fcntl.LOCK_UN)
            self._file.close()
            self._file = None


def database_ready(
    database: Database, directory: Path, minimum_bytes: int, *, check_schema: bool
) -> bool:
    if shutil.disk_usage(directory).free < minimum_bytes:
        return False
    with database.engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        if check_schema:
            return (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
                == SCHEMA_HEAD
            )
    return True
