"""Device identities and quota boundaries, independent of transport and storage."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo


class AccessDenied(Exception):
    def __init__(self, code: str, status: int = 403, retry_after: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.retry_after = retry_after


@dataclass(frozen=True, slots=True)
class DeviceIdentity:
    device_id: UUID
    installation_id: UUID
    expires_at: datetime


def quota_day(now: datetime) -> str:
    return now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()


def seconds_until_reset(now: datetime) -> int:
    local = now.astimezone(ZoneInfo("Asia/Shanghai"))
    midnight = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((midnight - local).total_seconds()))
