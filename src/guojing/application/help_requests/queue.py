"""Deterministic candidate selection for a recoverable worker."""

from collections.abc import Callable
from datetime import datetime, timedelta

from guojing.application.help_requests.service import HelpRequestService
from guojing.domain.help_requests import HelpRequestProcessingStatus, HelpRequestResult


class HelpRequestQueue:
    """Select pending work without changing lifecycle state or claiming a lease."""

    def __init__(
        self,
        service: HelpRequestService,
        *,
        clock: Callable[[], datetime] | None = None,
        processing_timeout: timedelta = timedelta(minutes=2),
    ) -> None:
        if processing_timeout <= timedelta(0):
            raise ValueError("processing_timeout must be positive")
        self._service = service
        self._clock = clock or service.current_time
        self._processing_timeout = processing_timeout

    def next_received(self) -> HelpRequestResult | None:
        """Return the oldest pending request, never a reviewed or terminal request."""
        pending = self._service.list_results(status=HelpRequestProcessingStatus.RECEIVED)
        return min(pending, key=lambda result: result.received_at, default=None)

    def next_pending(self) -> HelpRequestResult | None:
        """Return received work or processing work whose lease has gone stale."""
        received = self.next_received()
        if received is not None:
            return received
        cutoff = self._clock() - self._processing_timeout
        processing = self._service.list_results(status=HelpRequestProcessingStatus.PROCESSING)
        stale = tuple(result for result in processing if result.updated_at <= cutoff)
        return min(stale, key=lambda result: result.updated_at, default=None)
