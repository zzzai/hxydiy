"""Shared test fixtures.

Most regression fixtures model a store that is already accepting customers.
Store lifecycle tests still pass ``status=`` explicitly, which overrides this
test-only column default. Production default remains ``preparing``.
"""

from app.models import Store

Store.__table__.c.status.default.arg = "open"
