import pytest
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models import AuditLog, MembershipCard, Store, User
from scripts.import_member_cards import import_cards


PHONE = "13800138000"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Store(id=1, store_code="import-test", name="Test", address="Test"))
        session.commit()
        yield session
    engine.dispose()


def payload(**changes):
    row = dict(phone=PHONE, source_card_id="test-card", card_name="荷小悦会员卡",
               source_card_type="储值消费卡", started_at="2026-09-01T00:00:00+08:00",
               expires_at=None, balance_cents=100, allow_cross_store=False, status="active")
    row.update(changes)
    return {"source": "test_export", "store_code": "import-test", "cards": [row]}


def test_preview_is_readonly_and_apply_is_idempotent_without_profile_overwrite(db):
    user = User(openid="verified-existing", phone=PHONE, nickname="Keep", balance_cents=777)
    db.add(user); db.commit()
    result = import_cards(db, payload(), {PHONE}, apply=False)
    assert result["new_cards"] == 1
    assert db.scalar(select(func.count()).select_from(MembershipCard)) == 0
    first = import_cards(db, payload(), {PHONE}, apply=True)
    second = import_cards(db, payload(), {PHONE}, apply=True)
    assert first["new_cards"] == 1 and second["new_cards"] == 0
    assert db.scalar(select(func.count()).select_from(User)) == 1
    assert db.scalar(select(func.count()).select_from(MembershipCard)) == 1
    assert (user.nickname, user.openid, user.balance_cents, user.is_member) == ("Keep", "verified-existing", 777, False)
    assert db.scalar(select(AuditLog)).detail["classification_basis"] == "user_confirmed_card_classes_20260928"


def test_specific_annual_name_overrides_generic_type_and_keeps_original_dates(db):
    data = payload(card_name="荷小悦年度权益会员卡", expires_at="2027-09-01T00:00:00+08:00", balance_cents=0)
    result = import_cards(db, data, {PHONE}, apply=True)
    row = db.scalar(select(MembershipCard))
    assert result["new_cards"] == 1
    assert row.card_type == "annual"
    assert row.started_at.date().isoformat() == "2026-08-31"
    assert row.expires_at.date().isoformat() == "2027-08-31"


@pytest.mark.parametrize("changes", [{"phone": "13900139000"}, {"balance_cents": -1}, {"balance_cents": 1.1}, {"allow_cross_store": True}, {"started_at": "2026-09-01"}, {"status": None}])
def test_invalid_or_unauthorized_record_cannot_create_identity(db, changes):
    with pytest.raises(ValueError):
        import_cards(db, payload(**changes), {PHONE}, apply=True)
    assert db.scalar(select(func.count()).select_from(User)) == 0
    assert db.scalar(select(func.count()).select_from(MembershipCard)) == 0


def test_changed_snapshot_is_rejected_not_silently_updated(db):
    import_cards(db, payload(), {PHONE}, apply=True)
    with pytest.raises(ValueError, match="snapshot changed"):
        import_cards(db, payload(balance_cents=0), {PHONE}, apply=True)
    assert db.scalar(select(MembershipCard)).balance_cents == 100


def test_annual_import_cannot_extend_original_rights_to_multiple_years(db):
    with pytest.raises(ValueError, match="one original year"):
        import_cards(db, payload(card_name="荷小悦年度权益会员卡", expires_at="2036-09-01T00:00:00+08:00"),
                     {PHONE}, apply=True)
    assert db.scalar(select(func.count()).select_from(User)) == 0


def test_confirmed_two_card_mapping_does_not_invent_missing_status_or_dates(db):
    for changes in [{"status": None}, {"expires_at": None}, {"card_name": "unknown"}]:
        data = payload(card_name="荷小悦年度权益会员卡", expires_at="2027-09-01T00:00:00+08:00")
        data["cards"][0].update(changes)
        with pytest.raises(ValueError):
            import_cards(db, data, {PHONE}, apply=True)
    assert db.scalar(select(func.count()).select_from(User)) == 0


def test_late_identity_conflict_rolls_back_the_whole_batch(db):
    second_phone = "13900139000"
    db.add(User(openid="import_" + hashlib.sha256(second_phone.encode()).hexdigest()[:56]))
    db.commit()
    data = payload()
    data["cards"].append({**data["cards"][0], "phone": second_phone, "source_card_id": "second"})
    with pytest.raises(IntegrityError):
        import_cards(db, data, {PHONE, second_phone}, apply=True)
    assert db.scalar(select(func.count()).select_from(User)) == 1
    assert db.scalar(select(func.count()).select_from(MembershipCard)) == 0


def test_cli_apply_requires_backup_before_touching_database(tmp_path):
    phones = [f"1380000{index:04d}" for index in range(19)]
    source = tmp_path / "input.json"
    allowed = tmp_path / "allowed.txt"
    source.write_text(json.dumps(payload()), encoding="utf-8")
    allowed.write_text("\n".join(phones), encoding="utf-8")
    result = subprocess.run([sys.executable, "-m", "scripts.import_member_cards", str(source),
                             "--phones-file", str(allowed), "--apply"],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert result.returncode == 1
    assert "backup file and SHA256 required" in result.stderr
    assert PHONE not in result.stdout + result.stderr


def test_masked_phone_cannot_be_used_as_an_import_identity(db):
    masked = "138****8000"
    with pytest.raises(ValueError, match="invalid phone"):
        import_cards(db, payload(phone=masked), {masked}, apply=True)
    assert db.scalar(select(func.count()).select_from(User)) == 0


def test_valid_customer_status_does_not_imply_active_card(db):
    data = payload(status=None, customer_status="有效客", member_stage="临界会员",
                   card_name="荷小悦年度权益会员卡", expires_at="2027-09-01T00:00:00+08:00")
    with pytest.raises(ValueError, match="source card status"):
        import_cards(db, data, {PHONE}, apply=True)
    assert db.scalar(select(func.count()).select_from(MembershipCard)) == 0
