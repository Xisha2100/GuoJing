from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.models import Base, OperationsRecord
from guojing.operations.monitor import monitor


def test_pause_grace_expiry_and_recovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GUOJING_ALERT_WEBHOOK", raising=False)
    db = Database(f"sqlite:///{tmp_path / 'monitor.db'}")
    Base.metadata.create_all(db.engine)
    metrics = {"dependencies_ready": True, "accepting": False, "consecutive_failures": 0}
    client = MagicMock()
    client.__enter__.return_value.get.return_value.json.return_value = metrics
    with db.new_session() as session:
        session.add(OperationsRecord(key="backup_success_at", value=datetime.now(UTC).isoformat()))
        session.commit()
    try:
        with (
            patch("guojing.operations.monitor.httpx.Client", return_value=client),
            patch(
                "guojing.operations.monitor.shutil.disk_usage",
                return_value=SimpleNamespace(total=100, used=10),
            ),
            patch.object(Path, "read_text", return_value="MemTotal: 100\nMemAvailable: 90\n"),
        ):
            monitor(db)
            with db.new_session() as session:
                paused = session.get(OperationsRecord, "pause_observed_at")
                assert paused
                paused.value = (datetime.now(UTC) - timedelta(minutes=11)).isoformat()
                session.commit()
            with pytest.raises(RuntimeError, match="actionable"):
                monitor(db)
            metrics["accepting"] = True
            monitor(db)
            with db.new_session() as session:
                assert session.get(OperationsRecord, "pause_observed_at") is None
    finally:
        db.dispose()
