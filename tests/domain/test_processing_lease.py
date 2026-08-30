from datetime import UTC, datetime, timedelta

import pytest

from guojing.domain.processing_lease import ProcessingLease


def test_expired_lease_can_be_taken_over_but_not_renewed() -> None:
    acquired = datetime(2026, 8, 30, tzinfo=UTC)
    lease = ProcessingLease("worker-a", acquired, acquired + timedelta(minutes=1))

    assert lease.is_active_at(acquired + timedelta(seconds=59))
    assert lease.can_be_taken_over_at(acquired + timedelta(minutes=1))
    with pytest.raises(ValueError, match="expired"):
        lease.renew(acquired + timedelta(minutes=1), timedelta(minutes=1))


def test_active_owner_can_renew_a_lease() -> None:
    acquired = datetime(2026, 8, 30, tzinfo=UTC)
    lease = ProcessingLease("worker-a", acquired, acquired + timedelta(minutes=1))

    renewed = lease.renew(acquired + timedelta(seconds=30), timedelta(minutes=2))

    assert renewed.worker_id == "worker-a"
    assert renewed.expires_at == acquired + timedelta(minutes=2, seconds=30)
