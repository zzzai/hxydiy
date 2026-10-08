from datetime import datetime, timezone

import pytest

from app.domain.membership_pricing import confirmed_price_for_line


@pytest.mark.parametrize('member_type', ['annual', 'stored'])
def test_new_tuesday_confirmation_uses_member_price_without_automatic_gift(member_type):
    price = confirmed_price_for_line(
        {'store': 3990, 'member': 2990}, True,
        datetime(2026, 10, 13, 2, tzinfo=timezone.utc), 'Asia/Shanghai',
        datetime(2027, 10, 13, tzinfo=timezone.utc), member_type,
    )
    assert (price.amount_cents, price.basis) == (2990, 'member')
