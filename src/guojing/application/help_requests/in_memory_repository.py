"""In-memory Repository used by fast unit tests and isolated examples."""

from datetime import datetime
from threading import Lock
from uuid import UUID

from guojing.application.help_requests.ports import (
    ClientRequestConflictError,
)
from guojing.domain.help_requests import HelpRequestProcessingStatus, HelpRequestResult


class InMemoryHelpRequestRepository:
    """A bounded, TTL-aware test double with the same contract as SQL storage."""

    def __init__(self, *, max_results: int = 1_000) -> None:
        if max_results < 1:
            raise ValueError("max_results must be positive")
        self._max_results = max_results
        self._records: dict[UUID, tuple[HelpRequestResult, str, datetime]] = {}
        self._request_ids_by_client_id: dict[UUID, UUID] = {}
        self._lock = Lock()

    def create_or_get(
        self,
        result: HelpRequestResult,
        fingerprint: str,
        expires_at: datetime,
        now: datetime,
    ) -> HelpRequestResult:
        with self._lock:
            self._purge_expired(now)
            previous_id = self._request_ids_by_client_id.get(result.client_request_id)
            if previous_id is not None:
                previous, previous_fingerprint, _ = self._records[previous_id]
                if previous_fingerprint != fingerprint:
                    raise ClientRequestConflictError(
                        "client_request_id cannot be reused for different request data",
                    )
                return previous
            self._evict_if_full()
            self._records[result.request_id] = (result, fingerprint, expires_at)
            self._request_ids_by_client_id[result.client_request_id] = result.request_id
            return result

    def get(self, request_id: UUID, now: datetime) -> HelpRequestResult | None:
        with self._lock:
            self._purge_expired(now)
            stored = self._records.get(request_id)
            return stored[0] if stored is not None else None

    def list(
        self,
        status: HelpRequestProcessingStatus | None,
        now: datetime,
    ) -> tuple[HelpRequestResult, ...]:
        with self._lock:
            self._purge_expired(now)
            values = tuple(record[0] for record in self._records.values())
        if status is not None:
            values = tuple(value for value in values if value.processing_status is status)
        return tuple(sorted(values, key=lambda value: value.updated_at, reverse=True))

    def save(self, result: HelpRequestResult, now: datetime) -> None:
        with self._lock:
            self._purge_expired(now)
            stored = self._records.get(result.request_id)
            if stored is None:
                return
            _, fingerprint, expires_at = stored
            self._records[result.request_id] = (result, fingerprint, expires_at)

    def _purge_expired(self, now: datetime) -> None:
        expired = [
            request_id
            for request_id, (_, _, expires_at) in self._records.items()
            if expires_at <= now
        ]
        for request_id in expired:
            result, _, _ = self._records.pop(request_id)
            self._request_ids_by_client_id.pop(result.client_request_id, None)

    def _evict_if_full(self) -> None:
        while len(self._records) >= self._max_results:
            oldest_id = min(
                self._records,
                key=lambda request_id: self._records[request_id][0].updated_at,
            )
            oldest, _, _ = self._records.pop(oldest_id)
            self._request_ids_by_client_id.pop(oldest.client_request_id, None)
