"""Small-host alarms with numeric payloads and a 15-minute repeat interval."""

import json
import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.device_repository import SqlAlchemyDeviceRepository
from guojing.infrastructure.persistence.models import OperationsRecord
from guojing.infrastructure.runtime import ProcessLease


def monitor(database: Database) -> None:
    issues: list[str] = []
    try:
        with httpx.Client(timeout=8, trust_env=False) as client:
            response = client.get("http://127.0.0.1:8000/internal/status")
            response.raise_for_status()
            metrics = response.json()
        if not metrics["dependencies_ready"]:
            issues.append("service_unavailable")
        if metrics["consecutive_failures"] >= 3:
            issues.append("consecutive_analysis_failures")
        print(json.dumps({"metrics": metrics}))
    except Exception:
        issues.append("service_unavailable")
    disk = shutil.disk_usage(ProcessLease(str(database.engine.url)).directory)
    if disk.used / disk.total >= 0.8:
        issues.append("disk_above_80_percent")
    memory = {
        line.split(":")[0]: int(line.split()[1])
        for line in Path("/proc/meminfo").read_text().splitlines()
    }
    if 1 - memory["MemAvailable"] / memory["MemTotal"] >= 0.8:
        issues.append("memory_above_80_percent")
    now = datetime.now(UTC)
    with database.new_session() as db:
        backup = db.get(OperationsRecord, "backup_success_at")
        if backup is None or datetime.fromisoformat(backup.value) < now - timedelta(
            hours=6, minutes=15
        ):
            issues.append("backup_missing_or_stale")
        previous = db.get(OperationsRecord, "last_alarm_at")
        previous_time = datetime.fromisoformat(previous.value) if previous else None
        previous_codes = db.get(OperationsRecord, "last_alarm_codes")
        same_codes = previous_codes is not None and previous_codes.value == ",".join(issues)
    if issues:
        print(json.dumps({"alarm": issues}))
        webhook = os.environ.get("GUOJING_ALERT_WEBHOOK")
        if webhook and (
            not same_codes or previous_time is None or now - previous_time >= timedelta(minutes=15)
        ):
            if not webhook.startswith("https://"):
                raise ValueError("alert webhook requires HTTPS")
            with httpx.Client(timeout=10, trust_env=False) as client:
                result = client.post(webhook, json={"service": "guojing", "issues": issues})
                result.raise_for_status()
            with SqlAlchemyDeviceRepository(database).transaction() as db:
                db.merge(OperationsRecord(key="last_alarm_at", value=now.isoformat()))
                # Keep the bounded status field independent of message contents.
                db.merge(OperationsRecord(key="last_alarm_codes", value=",".join(issues)))
        raise RuntimeError("monitor detected an actionable condition")
