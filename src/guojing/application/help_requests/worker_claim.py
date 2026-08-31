"""Compose queue selection and short-lived ownership into one worker decision."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from guojing.application.help_requests.queue import HelpRequestQueue
from guojing.domain.help_requests import HelpRequestResult
from guojing.domain.processing_lease import ProcessingLease


@dataclass(frozen=True, slots=True)
class WorkerClaim:
    request: HelpRequestResult
    lease: ProcessingLease


class HelpRequestWorkerClaimer:
    def __init__(
        self,
        queue: HelpRequestQueue,
        lease_duration: timedelta = timedelta(minutes=2),
    ) -> None:
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        self._queue = queue
        self._lease_duration = lease_duration

    def claim(self, worker_id: str, now: datetime) -> WorkerClaim | None:
        request = self._queue.next_pending()
        if request is None:
            return None
        return WorkerClaim(request, ProcessingLease(worker_id, now, now + self._lease_duration))
