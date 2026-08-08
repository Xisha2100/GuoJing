"""Interactive account-management command behavior."""

from pathlib import Path

import pytest
from sqlalchemy import select

from guojing.cli import main
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.models import AdminUserRecord, Base
from tests.auth_helpers import FastPasswordHasher


def test_create_admin_reads_password_interactively(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_url = f"sqlite:///{tmp_path / 'cli.db'}"
    database = Database(database_url)
    Base.metadata.create_all(database.engine)
    database.dispose()
    monkeypatch.setenv("GUOJING_DATABASE_URL", database_url)
    prompts: list[str] = []

    def read_password(prompt: str) -> str:
        prompts.append(prompt)
        return "interactive-test-password"

    exit_code = main(
        ["create-admin", "--username", "Family.Admin"],
        password_reader=read_password,
        password_hasher=FastPasswordHasher(),
    )

    verification_database = Database(database_url)
    with verification_database.new_session() as session:
        record = session.scalar(select(AdminUserRecord))
    verification_database.dispose()
    assert exit_code == 0
    assert prompts == ["Password: ", "Confirm password: "]
    assert record is not None
    assert record.username == "family.admin"
    assert "interactive-test-password" not in record.password_hash
    assert "Created administrator 'family.admin'." in capsys.readouterr().out
