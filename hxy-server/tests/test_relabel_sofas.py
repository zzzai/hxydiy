import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models import Order, Room, SelectionSession, Store, User
from app.models.occupancy import PositionOccupancy
from app.models.service_position_qr import ServicePositionQr
from app.api.occupancies import _managed_position_qr_token, _managed_position_short_code, resolve_position_qr_token
from scripts.relabel_sofas import relabel_sofas


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        db.add(Store(id=1, name="Test", store_code="test", address="Test"))
        for i, label in enumerate([1, 2, 3, 5, 6, 7, 8, 9], 1):
            db.add(Room(id=i, store_id=1, code=f"sofa-{i:02}",
                        name=f"{label}号沙发", customer_label=f"{label}号沙发",
                        room_type="sofa", map_x=0.08 if i <= 4 else 0.7,
                        map_y=[0.14, 0.34, 0.54, 0.74][(i - 1) % 4],
                        status="occupied" if i == 1 else "available"))
        db.commit()
        yield db
    engine.dispose()


def values(db):
    return [dict(id=r.id, code=r.code, name=r.name, label=r.customer_label,
                 x=r.map_x, y=r.map_y, status=r.status, version=r.version)
            for r in db.scalars(select(Room).order_by(Room.id))]


def test_preview_does_not_write(db):
    before = values(db)
    report = relabel_sofas(db)
    db.commit()
    assert report["changed"] == 8
    assert values(db) == before


def test_apply_changes_only_names_and_is_idempotent(db):
    before = values(db)
    assert relabel_sofas(db, apply=True)["changed"] == 8
    db.commit()
    after = values(db)
    assert [r["label"] for r in after] == [f"{n}号沙发" for n in [5, 3, 2, 1, 9, 8, 7, 6]]
    for old, new in zip(before, after):
        assert new["name"] == new["label"]
        assert {k: v for k, v in old.items() if k not in ("name", "label")} == {
            k: v for k, v in new.items() if k not in ("name", "label")}
    assert relabel_sofas(db, apply=True)["changed"] == 0


def test_restore_is_guarded_and_idempotent(db):
    before = values(db)
    relabel_sofas(db, apply=True)
    db.commit()
    assert relabel_sofas(db, apply=True, restore=True)["changed"] == 8
    db.commit()
    assert values(db) == before
    assert relabel_sofas(db, apply=True, restore=True)["changed"] == 0


@pytest.mark.parametrize("field,value", [("map_y", 0.2), ("code", "changed"),
                                        ("customer_label", "Unknown"), ("store_id", 2)])
def test_mapping_drift_refuses_all_writes(db, field, value):
    setattr(db.get(Room, 8), field, value)
    db.commit()
    before = values(db)
    with pytest.raises(ValueError):
        relabel_sofas(db, apply=True)
    db.rollback()
    assert values(db) == before


def test_duplicate_label_outside_targets_refuses_update(db):
    db.add(Room(id=9, store_id=1, code="other", name="Other",
                customer_label="5号沙发", room_type="bed"))
    db.commit()
    with pytest.raises(ValueError):
        relabel_sofas(db, apply=True)
    db.rollback()
    assert db.get(Room, 1).name == "1号沙发"


def test_old_tokens_and_active_and_historical_references_are_unchanged(db):
    db.add(User(id=1, openid="synthetic"))
    db.add(Order(id=1, order_no="SYNTHETIC", order_type="service", user_id=1,
                 store_id=1, items=[{"position_label": "1号沙发"}], status="completed"))
    db.add(SelectionSession(id="synthetic", access_token_hash="x" * 64, store_id=1,
                            customer_id=1, pricing_snapshot={"position_label": "1号沙发"}))
    db.add(PositionOccupancy(id=1, store_id=1, room_id=1, active_room_id=1,
                             selection_session_id="synthetic", active_session_id="synthetic",
                             status="in_service"))
    for i in range(1, 9):
        db.add(ServicePositionQr(id=i + 2, public_id=f"00000000-0000-0000-0000-{i:012}",
                                 store_id=1, room_id=i, status="active", short_code_hash=str(i) * 64))
    db.commit()
    tables = ["orders", "position_occupancies", "selection_sessions", "service_position_qrs"]
    before = {table: list(db.execute(text(f"SELECT * FROM {table}"))) for table in tables}
    credentials = [(_managed_position_qr_token(db.get(ServicePositionQr, i + 2), f"sofa-{i:02}"),
                    _managed_position_short_code(db.get(ServicePositionQr, i + 2))) for i in range(1, 9)]
    relabel_sofas(db, apply=True)
    db.commit()
    assert {table: list(db.execute(text(f"SELECT * FROM {table}"))) for table in tables} == before
    with db.no_autoflush:
        for i, (token, short) in enumerate(credentials, 1):
            qr, room = resolve_position_qr_token(db, token)
            assert (qr.id, room.id, room.code) == (i + 2, i, f"sofa-{i:02}")
            assert room.customer_label == ["5号沙发", "3号沙发", "2号沙发", "1号沙发",
                                           "9号沙发", "8号沙发", "7号沙发", "6号沙发"][i - 1]
            assert _managed_position_qr_token(qr, room.code) == token
            assert _managed_position_short_code(qr) == short
    db.rollback()
