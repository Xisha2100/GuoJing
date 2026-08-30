from datetime import timedelta

from guojing.application.help_requests.failure_resolution import HelpRequestFailureResolver
from guojing.domain.retry_policy import RetryPolicy


def test_failure_resolution_stops_at_retry_budget() -> None:
    resolver = HelpRequestFailureResolver(
        RetryPolicy(max_attempts=2, initial_delay=timedelta(seconds=1))
    )
    assert resolver.resolve(1).retry_after == timedelta(seconds=1)
    assert resolver.resolve(1).requires_human_review is False
    assert resolver.resolve(2).requires_human_review is True
