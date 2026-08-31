"""In-memory Repository used by fast unit tests and isolated examples."""

from datetime import datetime
from threading import Lock
from uuid import UUID

from guojing.application.help_requests.ports import (
    ClientRequestConflictError,
    HelpRequestCapacityError,
    HelpRequestStateConflictError,
)
from guojing.domain.help_requests import (
    HelpRequestProcessingStatus,
    HelpRequestResult,
)


class InMemoryHelpRequestRepository:
    """A bounded, TTL-aware test double with the same contract as SQL storage."""

    def __init__(self, *, max_results: int = 1_000) -> None:
        if max_results < 1:
            raise ValueError("max_results must be positive")
        self._max_results = max_results
        self._records: dict[UUID, tuple[HelpRequestResult, str, tuple[str, ...], datetime]] = {}
        self._request_ids_by_client_id: dict[UUID, UUID] = {}
        self._lock = Lock()

    def create_or_get(
        self,
        result: HelpRequestResult,
        fingerprint: str,
        expires_at: datetime,
        access_token_digest: str,
        now: datetime,
    ) -> HelpRequestResult:
        with self._lock:
            self._purge_expired(now)
            previous_id = self._request_ids_by_client_id.get(result.client_request_id)
            if previous_id is not None:
                previous, previous_fingerprint, previous_digests, previous_expiry = self._records[
                    previous_id
                ]
                if previous_fingerprint != fingerprint:
                    raise ClientRequestConflictError(
                        "client_request_id cannot be reused for different request data",
                    )
                self._records[previous_id] = (
                    previous,
                    previous_fingerprint,
                    _append_digest(previous_digests, access_token_digest),
                    previous_expiry,
                )
                return previous
            self._evict_if_full()
            self._records[result.request_id] = (
                result,
                fingerprint,
                (access_token_digest,),
                expires_at,
            )
            self._request_ids_by_client_id[result.client_request_id] = result.request_id
            return result

    def get(self, request_id: UUID, now: datetime) -> HelpRequestResult | None:
        with self._lock:
            self._purge_expired(now)
            stored = self._records.get(request_id)
            return stored[0] if stored is not None else None

    def is_access_authorized(
        self,
        request_id: UUID,
        access_token_digest: str,
        now: datetime,
    ) -> bool:
        with self._lock:
            self._purge_expired(now)
            stored = self._records.get(request_id)
            return stored is not None and access_token_digest in stored[2]

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

    def save(self, result: HelpRequestResult, expected_version: int, now: datetime) -> None:
        with self._lock:
            self._purge_expired(now)
            stored = self._records.get(result.request_id)
            if stored is None:
                raise HelpRequestStateConflictError("help request result no longer exists")
            current, fingerprint, access_token_digests, expires_at = stored
            if current.state_version != expected_version:
                raise HelpRequestStateConflictError(
                    "help request result was updated by another worker",
                )
            if result.state_version != expected_version + 1:
                raise ValueError("state transition must increment state_version by one")
            self._records[result.request_id] = (
                result,
                fingerprint,
                access_token_digests,
                expires_at,
            )

    def _purge_expired(self, now: datetime) -> None:
        expired = [
            request_id
            for request_id, (_, _, _, expires_at) in self._records.items()
            if expires_at <= now
        ]
        for request_id in expired:
            result, _, _, _ = self._records.pop(request_id)
            self._request_ids_by_client_id.pop(result.client_request_id, None)

    def _evict_if_full(self) -> None:
        while len(self._records) >= self._max_results:
            evictable = [
                request_id
                for request_id, (result, _, _, _) in self._records.items()
                if result.processing_status is HelpRequestProcessingStatus.GUIDANCE_READY
            ]
            if not evictable:
                raise HelpRequestCapacityError(
                    "help request capacity is full; active requests are never evicted",
                )
            oldest_id = min(
                evictable,
                key=lambda request_id: self._records[request_id][0].updated_at,
            )
            oldest, _, _, _ = self._records.pop(oldest_id)
            self._request_ids_by_client_id.pop(oldest.client_request_id, None)


def _append_digest(previous: tuple[str, ...], digest: str, *, limit: int = 8) -> tuple[str, ...]:
    """Keep a small overlap window so late idempotent receipts remain valid."""
    if digest in previous:
        return previous
    return (*previous, digest)[-limit:]
