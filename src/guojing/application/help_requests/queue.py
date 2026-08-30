"""Deterministic candidate selection for a future background worker."""

from guojing.application.help_requests.service import HelpRequestService
from guojing.domain.help_requests import HelpRequestProcessingStatus, HelpRequestResult


class HelpRequestQueue:
    """Select pending work without changing lifecycle state or claiming a lease."""

    def __init__(self, service: HelpRequestService) -> None:
        self._service = service

    def next_received(self) -> HelpRequestResult | None:
        """Return the oldest pending request, never a reviewed or terminal request."""
        pending = self._service.list_results(status=HelpRequestProcessingStatus.RECEIVED)
        return min(pending, key=lambda result: result.received_at, default=None)
