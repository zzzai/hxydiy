from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.store_lifecycle import require_store_open


def test_open_and_trial_store_accept_business():
    assert require_store_open(SimpleNamespace(status="open")).status == "open"
    assert require_store_open(SimpleNamespace(status="trial_open")).status == "trial_open"


@pytest.mark.parametrize("status", ["preparing", "suspended", "closed"])
def test_non_open_store_rejects_new_business(status):
    with pytest.raises(HTTPException) as error:
        require_store_open(SimpleNamespace(status=status), "下单")
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "STORE_NOT_OPEN"
    assert error.value.detail["store_status"] == status


def test_missing_store_is_404():
    with pytest.raises(HTTPException) as error:
        require_store_open(None)
    assert error.value.status_code == 404
