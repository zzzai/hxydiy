from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.store_lifecycle import require_store_open, validate_store_transition


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


def test_store_lifecycle_only_allows_documented_transitions():
    validate_store_transition("preparing", "open")
    validate_store_transition("open", "suspended")
    validate_store_transition("suspended", "open")
    validate_store_transition("open", "closed")
    with pytest.raises(HTTPException) as error:
        validate_store_transition("preparing", "suspended")
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "INVALID_STORE_TRANSITION"
    with pytest.raises(HTTPException):
        validate_store_transition("closed", "open")
