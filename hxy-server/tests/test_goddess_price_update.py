"""Verify the scoped price change, real catalog output and historical protection."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.catalog import _project_to_out
from app.db.session import Base
from app.domain.membership_pricing import price_book_prices
from app.domain.selection_pricing import calculate_selection_pricing
from app.models import AuditLog, PriceBook, Project, Store
from scripts.reconcile_goddess_price_20261113 import CODE, reconcile_price, snapshot


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Store(id=1, store_code="hxy-anyang-ziwei-001", name="Synthetic", address="Synthetic"))
        session.add(Store(id=2, store_code="other-store", name="Other", address="Synthetic"))
        session.add(Project(id=16, code=CODE, name="Goddess", store_id=1, category="bath", publication_status="published"))
        session.add(Project(id=17, code="other-project", name="Other", store_id=2, category="bath", publication_status="published"))
        session.flush()
        for kind, amount in [("store", 10900), ("member", 7900), ("group", 8900)]:
            session.add(PriceBook(project_id=16, price_type=kind, amount_cents=amount, version="old"))
        session.add(PriceBook(project_id=16, price_type="store", amount_cents=9900, version="historic",
                              effective_to=datetime.now(UTC) - timedelta(days=1)))
        session.add(PriceBook(project_id=17, price_type="store", amount_cents=8900, version="other"))
        session.commit()
        yield session
    engine.dispose()


def test_price_catalog_quote_history_and_idempotence(db):
    before = {row.id: snapshot(row) for row in db.scalars(select(PriceBook))}
    old_quote = calculate_selection_pricing(db, [{"project_id": 16, "quantity": 1}], "store")
    preview = reconcile_price(db)
    assert preview["change_count"] == 1
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0
    reconcile_price(db, apply=True, expected_hash=preview["preview_hash"])
    db.commit()
    assert price_book_prices(db, 16) == {"store": 11900, "member": 7900, "group": 8900}
    output = _project_to_out(db, db.get(Project, 16))
    assert output.half_price_coupon_price_cents == 5950
    assert {p.price_type: p.amount_cents for p in output.prices} == {"store": 11900, "member": 7900, "group": 8900}
    new_quote = calculate_selection_pricing(db, [{"project_id": 16, "quantity": 1}], "store")
    assert new_quote != old_quote
    for identity, original in before.items():
        current = snapshot(db.get(PriceBook, identity))
        if original["project_id"] == 16 and original["price_type"] == "store" and original["effective_to"] is None:
            assert current.pop("effective_to") is not None
            original.pop("effective_to")
        assert current == original
    assert db.scalar(select(func.count()).select_from(PriceBook)) == len(before) + 1
    replay = reconcile_price(db)
    assert replay["change_count"] == 0
    reconcile_price(db, apply=True, expected_hash=replay["preview_hash"])
    db.commit()
    assert db.scalar(select(func.count()).select_from(PriceBook)) == len(before) + 1
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 1


@pytest.mark.parametrize("field,value,error", [
    ("store_id", 2, "scope_changed"),
    ("category", "balance", "scope_changed"),
    ("publication_status", "archived", "scope_changed"),
])
def test_wrong_scope_stops(db, field, value, error):
    setattr(db.get(Project, 16), field, value)
    db.commit()
    with pytest.raises(ValueError, match=error):
        reconcile_price(db)


def test_stale_preview_stops_before_mutation(db):
    preview = reconcile_price(db)
    db.get(Project, 16).summary = "Changed by another editor"
    db.commit()
    with pytest.raises(ValueError, match="preview_changed"):
        reconcile_price(db, apply=True, expected_hash=preview["preview_hash"])
    db.rollback()
    assert price_book_prices(db, 16)["store"] == 10900
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_unexpected_member_price_stops(db):
    row = db.scalar(select(PriceBook).where(PriceBook.project_id == 16, PriceBook.price_type == "member"))
    row.amount_cents = 6900
    db.commit()
    with pytest.raises(ValueError, match="baseline_changed"):
        reconcile_price(db)
