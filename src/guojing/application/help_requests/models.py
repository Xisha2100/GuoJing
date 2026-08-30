"""Application models for the transient screenshot help receiver."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from guojing.domain.help_requests import (
    HelpRequestIntent,
    HelpRequestProcessingRoute,
    HelpRequestProcessingStatus,
)


@dataclass(frozen=True, slots=True)
class HelpRequestReceipt:
    """A receipt that records validation and routing, not an AI answer."""

    request_id: UUID
    client_request_id: UUID
    intent: HelpRequestIntent
    processing_route: HelpRequestProcessingRoute
    received_at: datetime
    access_token: str
    processing_status: HelpRequestProcessingStatus = HelpRequestProcessingStatus.RECEIVED
    image_disposition: str = "discarded_after_validation"
