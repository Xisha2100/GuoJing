"""Device admission and execution accounting ports."""

import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Protocol
from uuid import UUID

from guojing.domain.device_access import AccessDenied, DeviceIdentity


class AccessRepository(Protocol):
    def invite(self, digest: str, label: str, expires_at: datetime) -> None: ...

    def activate(
        self,
        invite_digest: str,
        installation_id: UUID,
        secret_digest: str,
        now: datetime,
        expires_at: datetime,
        maximum_devices: int,
    ) -> DeviceIdentity: ...

    def authenticate(self, device_id: UUID, digest: str, now: datetime) -> DeviceIdentity: ...

    def require_active(self, device_id: UUID, now: datetime) -> None: ...

    def reserve(
        self,
        run_id: UUID,
        device_id: UUID,
        now: datetime,
        device_limit: int,
        global_limit: int,
    ) -> None: ...

    def start(self, run_id: UUID, now: datetime) -> None: ...

    def finish(self, run_id: UUID) -> None: ...

    def recover(self) -> None: ...

    def accepting(self) -> bool: ...


class DeviceAccessService:
    def __init__(
        self,
        repository: AccessRepository,
        *,
        maximum_devices: int = 10,
        device_limit: int = 50,
        global_limit: int = 300,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(UTC))
        self._maximum_devices = maximum_devices
        self._device_limit = device_limit
        self._global_limit = global_limit

    def invite(self, label: str) -> str:
        code = secrets.token_urlsafe(32)
        self._repository.invite(_digest(code), label, self._clock() + timedelta(days=7))
        return code

    def activate(self, code: str, installation_id: UUID, secret: str) -> DeviceIdentity:
        now = self._clock()
        return self._repository.activate(
            _digest(code),
            installation_id,
            _digest(secret),
            now,
            now + timedelta(days=90),
            self._maximum_devices,
        )

    def authenticate(self, authorization: str) -> DeviceIdentity:
        try:
            scheme, value = authorization.split(" ", 1)
            identifier, secret = value.split(".", 1)
            if scheme.lower() != "bearer" or not 32 <= len(secret) <= 128:
                raise ValueError
            device_id = UUID(identifier)
        except ValueError as error:
            raise AccessDenied("device_credentials_required", 401) from error
        return self._repository.authenticate(device_id, _digest(secret), self._clock())

    def require_active(self, device_id: UUID) -> None:
        self._repository.require_active(device_id, self._clock())

    def reserve(self, run_id: UUID, device_id: UUID) -> None:
        self._repository.reserve(
            run_id,
            device_id,
            self._clock(),
            self._device_limit,
            self._global_limit,
        )

    def start(self, run_id: UUID) -> None:
        self._repository.start(run_id, self._clock())

    def finish(self, run_id: UUID) -> None:
        self._repository.finish(run_id)

    def recover(self) -> None:
        self._repository.recover()

    def accepting(self) -> bool:
        return self._repository.accepting()


def _digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()
