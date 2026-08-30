"""Translate a bounded retry calculation into an explicit worker decision."""

from dataclasses import dataclass
from datetime import timedelta

from guojing.domain.retry_policy import RetryPolicy


@dataclass(frozen=True, slots=True)
class FailureResolution:
    retry_after: timedelta | None
    requires_human_review: bool


class HelpRequestFailureResolver:
    def __init__(self, retry_policy: RetryPolicy | None = None) -> None:
        self._retry_policy = retry_policy or RetryPolicy()

    def resolve(self, attempt_number: int) -> FailureResolution:
        delay = self._retry_policy.delay_after_failure(attempt_number)
        return FailureResolution(retry_after=delay, requires_human_review=delay is None)
