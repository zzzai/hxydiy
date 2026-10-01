import pytest

from scripts.update_member_card_facts import input_digest, prepare_request


def test_tool_defaults_to_preview_and_scopes_store():
    path, body = prepare_request({"card_id": 1, "store_id": 2, "balance_cents": 0})
    assert path.endswith("/1/facts?store_id=2")
    assert body == {"balance_cents": 0, "apply": False}


def test_apply_requires_exact_preview_input_and_forwards_proof():
    payload = {"card_id": 1, "balance_cents": 0, "idempotency_key": "tested-request"}
    preview = {"input_sha256": input_digest(payload), "applied": False, "version": "v", "preview_token": "p"}
    _, body = prepare_request(payload, preview)
    assert body["apply"] and body["expected_version"] == "v" and body["preview_token"] == "p"
    with pytest.raises(ValueError):
        prepare_request({**payload, "balance_cents": 1}, preview)


@pytest.mark.parametrize("payload", [{"card_id": True}, {"card_id": 0}, {"card_id": 1, "apply": True},
                                     {"card_id": 1, "expected_version": "blind"}])
def test_tool_rejects_blind_control_fields_and_invalid_identifiers(payload):
    with pytest.raises(ValueError):
        prepare_request(payload)
