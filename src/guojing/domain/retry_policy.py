"""Bounded retry scheduling for non-terminal help-request processing."""

from datetime import timedelta
from typing import cast


class RetryPolicy:
    """Calculate capped exponential backoff without sleeping or performing I/O."""

    def __init__(
        self,
        *,
        max_attempts: int = 3,
        initial_delay: timedelta = timedelta(seconds=5),
        max_delay: timedelta = timedelta(minutes=1),
    ) -> None:
        if max_attempts < 1 or initial_delay <= timedelta(0) or max_delay < initial_delay:
            raise ValueError("retry policy bounds are invalid")
        self._max_attempts = max_attempts
        self._initial_delay = initial_delay
        self._max_delay = max_delay

    def delay_after_failure(self, attempt_number: int) -> timedelta | None:
        """Return no delay when the recorded failure exhausts the retry budget."""
        if attempt_number < 1:
            raise ValueError("attempt_number must be positive")
        if attempt_number >= self._max_attempts:
            return None
        delay = cast(timedelta, self._initial_delay * (2 ** (attempt_number - 1)))
        return min(delay, self._max_delay)
