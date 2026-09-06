from app.models import CustomerProfileConsent, CustomerProfileCurrent


def test_current_profile_model_keeps_rebuild_source_expiry_and_confirmation_count():
    table = CustomerProfileCurrent.__table__

    assert table.c.customer_id.nullable is False
    assert table.c.source_record_id.nullable is False
    assert table.c.profile_value_json.nullable is False
    assert table.c.confirmation_count.nullable is False
    assert table.c.valid_until.nullable is False


def test_profile_consent_model_is_versioned_and_revocable():
    table = CustomerProfileConsent.__table__

    assert table.c.consent_type.nullable is False
    assert table.c.consent_text_version.nullable is False
    assert table.c.revoked_at.nullable is True
