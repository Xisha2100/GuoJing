from datetime import timedelta

from guojing.domain.retry_policy import RetryPolicy


def test_retry_policy_caps_exponential_delay_and_stops_at_budget() -> None:
    policy = RetryPolicy(
        max_attempts=4,
        initial_delay=timedelta(seconds=5),
        max_delay=timedelta(seconds=12),
    )

    assert policy.delay_after_failure(1) == timedelta(seconds=5)
    assert policy.delay_after_failure(2) == timedelta(seconds=10)
    assert policy.delay_after_failure(3) == timedelta(seconds=12)
    assert policy.delay_after_failure(4) is None
