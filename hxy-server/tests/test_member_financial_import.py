"""Transaction and identity checks use synthetic customers and amounts only."""
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256

import os
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.engine import make_url

import pytest
from sqlalchemy import create_engine, select, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models import Store, User, MembershipCard, MembershipBalanceSnapshot, MembershipConsumptionBatch, MembershipConsumptionBill
from app.domain.member_consumption import BillLine, ConsumptionBill
from app.services import member_financial_import as imp

NOW = datetime(2026, 11, 15, 1, tzinfo=UTC)
PHONE = "13900000001"
RAW = " 00001"


@pytest.fixture
def factory():
    url=os.environ.get("MEMBER_FINANCE_TEST_DATABASE_URL")
    if url:
        parsed=make_url(url)
        assert parsed.host == "127.0.0.1" and parsed.database == "member_finance_test"
        assert parsed.port and parsed.port != 5432
        engine=create_engine(url)
    else:
        engine=create_engine("sqlite://",poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions=sessionmaker(engine,expire_on_commit=False)
    with sessions.begin() as db:
        db.add(Store(id=1,store_code="hxy-anyang-ziwei-001",name="Synthetic",address="Synthetic"))
        db.add(User(id=1,openid="synthetic-finance-owner",phone=PHONE,nickname="Synthetic",balance_cents=321))
        db.flush()
        db.add(MembershipCard(id=1,user_id=1,store_id=1,source="meiguanjia_export",source_card_key=sha256(("hxy-anyang-ziwei-001"+chr(0)+RAW).encode()).hexdigest(),card_type="stored",started_at=NOW,expires_at=None,balance_cents=10000,status="active",observed_at=NOW))
    yield sessions
    if url:
        Base.metadata.drop_all(engine)
    engine.dispose()


def seal(value):
    return replace(value,manifest_sha256=imp.packet_sha256(value))


def packet():
    bill=ConsumptionBill(source_bill_no="SYN-01",source_row_sha256="a"*64,store_id=1,user_id=None,bill_type="service",bill_status="normal_settled",attribution_status="owned",refund_status="none",payment_evidence_complete=True,occurred_at=NOW,settled_at=NOW,store_price_total_cents=11900,settled_total_cents=7900,cash_payment_cents=7900,card_principal_debit_cents=0,card_bonus_debit_cents=0,coupon_payment_cents=0,other_payment_cents=0,lines=(BillLine("Synthetic",1,11900,7900,line_order=1),))
    return seal(imp.FinancialBatch(batch_key="synthetic-01",source_snapshot_sha256="b"*64,manifest_sha256="c"*64,query_range_start=NOW,query_range_end=NOW,observed_at=NOW,page_count=1,last_page_complete=True,coverage_gaps={"refunds":"synthetic test evidence"},evidence_ref="synthetic/receipt.json",bills=(imp.SourceBill(RAW,PHONE,bill,"synthetic/bill.json"),),balances=(imp.SourceBalance(RAW,PHONE,NOW,9000,None,None,"synthetic/balance.json"),)))


def old_facts(sessions):
    with sessions() as db:
        return [tuple(db.execute(select(*model.__table__.columns)).first()) for model in (User, MembershipCard)]


def test_preview_apply_replay_and_old_facts(factory):
    before=old_facts(factory)
    preview=imp.execute(factory,packet())
    assert preview["insert_bills"] == 1 and preview["insert_balances"] == 1
    with factory() as db:
        assert db.scalars(select(MembershipConsumptionBatch)).all()==[]
    result=imp.execute(factory,packet(),apply=True)
    assert result["status"]=="applied"
    assert imp.execute(factory,packet(),apply=True)["status"]=="already_applied"
    assert old_facts(factory)==before
    with factory() as db:
        assert len(db.scalars(select(MembershipConsumptionBill)).all())==1
        assert len(db.scalars(select(MembershipBalanceSnapshot)).all())==1
        assert db.get(MembershipConsumptionBill,1).user_id==1
        assert db.get(MembershipBalanceSnapshot,1).principal_cents is None


@pytest.mark.parametrize("raw,phone",[(RAW.strip(),PHONE),(RAW,"13900000002")])
def test_exact_card_and_phone_required(factory,raw,phone):
    p=packet()
    p=replace(p,balances=(replace(p.balances[0],card_number=raw,phone=phone),))
    with pytest.raises(imp.ImportBlocked):
        imp.execute(factory,seal(p),apply=True)
    with factory() as db:
        assert not db.scalars(select(MembershipConsumptionBatch)).all()


def test_reused_batch_key_with_changed_manifest_is_rejected(factory):
    imp.execute(factory,packet(),apply=True)
    with pytest.raises(imp.ImportBlocked,match="manifest_content_mismatch"):
        imp.execute(factory,replace(packet(),manifest_sha256="d"*64),apply=True)


def test_changed_bill_appends_conflict_without_overwriting_original(factory):
    p=packet()
    imp.execute(factory,p,apply=True)
    changed=replace(p.bills[0],bill=replace(p.bills[0].bill,refund_status="partial"))
    result=imp.execute(factory,seal(replace(p,batch_key="synthetic-02",bills=(changed,))),apply=True)
    assert result["conflicting_bill_groups"]==1
    with factory() as db:
        bills=db.scalars(select(MembershipConsumptionBill).order_by(MembershipConsumptionBill.id)).all()
        assert [b.refund_status for b in bills]==["none","partial"]
        assert len(db.scalars(select(MembershipBalanceSnapshot)).all())==1


def test_failure_after_partial_flush_rolls_back_whole_batch(factory):
    engine=factory.kw["bind"]
    def fail(conn,cursor,statement,parameters,context,executemany):
        if statement.startswith("INSERT INTO membership_balance_snapshots"):
            raise RuntimeError("synthetic_storage_failure")
    event.listen(engine,"before_cursor_execute",fail)
    try:
        with pytest.raises(RuntimeError,match="synthetic_storage_failure"):
            imp.execute(factory,packet(),apply=True)
    finally:
        event.remove(engine,"before_cursor_execute",fail)
    with factory() as db:
        assert not db.scalars(select(MembershipConsumptionBatch)).all()
        assert not db.scalars(select(MembershipConsumptionBill)).all()


@pytest.mark.parametrize("bad",[{"line_order":0},{"quantity":1.5},{"quantity":-1}])
def test_invalid_line_rejected_during_preview(factory,bad):
    p=packet()
    bad_line=replace(p.bills[0].bill.lines[0],**bad)
    changed=replace(p.bills[0],bill=replace(p.bills[0].bill,lines=(bad_line,)))
    with pytest.raises(imp.ImportBlocked):
        imp.execute(factory,seal(replace(p,bills=(changed,))))


def test_balance_conflict_does_not_replace_old_snapshot(factory):
    p=packet()
    imp.execute(factory,p,apply=True)
    changed=replace(p.balances[0],total_cents=8000)
    with pytest.raises(imp.ImportBlocked,match="balance_observation_conflict"):
        imp.execute(factory,seal(replace(p,batch_key="synthetic-02",balances=(changed,))),apply=True)
    with factory() as db:
        assert len(db.scalars(select(MembershipConsumptionBatch)).all())==1
        assert db.get(MembershipBalanceSnapshot,1).total_cents==9000


def test_changed_facts_under_same_signed_manifest_are_rejected(factory):
    p=packet()
    changed=replace(p,balances=(replace(p.balances[0],total_cents=1),))
    with pytest.raises(imp.ImportBlocked,match="manifest_content_mismatch"):
        imp.execute(factory,changed,apply=True)


def test_identical_facts_under_new_batch_key_are_zero_writes(factory):
    p=packet()
    imp.execute(factory,p,apply=True)
    result=imp.execute(factory,seal(replace(p,batch_key="synthetic-02")),apply=True)
    assert result["status"]=="no_new" and result["business_writes"]==0
    with factory() as db:
        assert len(db.scalars(select(MembershipConsumptionBatch)).all())==1


def test_resigned_changed_batch_cannot_replace_same_key(factory):
    p=packet()
    imp.execute(factory,p,apply=True)
    changed=seal(replace(p,source_snapshot_sha256="d"*64))
    with pytest.raises(imp.ImportBlocked,match="batch_identity_conflict"):
        imp.execute(factory,changed,apply=True)


def test_projection_uses_imported_fact_and_hides_other_customer(factory):
    from app.services.customer_consumption import build_customer_consumption_history
    p=packet()
    imp.execute(factory,p,apply=True)
    with factory.begin() as db:
        db.add(User(id=2,openid="synthetic-unrelated",phone="13900000002",nickname="Other"))
    with factory() as db:
        own=build_customer_consumption_history(db,db.get(User,1))
        other=build_customer_consumption_history(db,db.get(User,2))
        assert own["savings"]["amount_cents"]==4000
        assert own["pagination"]["total"]==1
        assert other["bills"]==[] and other["savings"]["amount_cents"] is None
    changed=replace(p.bills[0],bill=replace(p.bills[0].bill,refund_status="partial"))
    imp.execute(factory,seal(replace(p,batch_key="synthetic-revision",bills=(changed,))),apply=True)
    with factory() as db:
        own=build_customer_consumption_history(db,db.get(User,1))
        assert own["bills"]==[] and own["savings"]["amount_cents"] is None


@pytest.mark.skipif(not os.environ.get("MEMBER_FINANCE_TEST_DATABASE_URL"),reason="isolated PostgreSQL required")
def test_concurrent_exact_batch_commits_once(factory):
    p=packet()
    with ThreadPoolExecutor(max_workers=2) as workers:
        results=list(workers.map(lambda _: imp.execute(factory,p,apply=True),range(2)))
    assert sorted(row["status"] for row in results)==["already_applied","applied"]
    with factory() as db:
        assert len(db.scalars(select(MembershipConsumptionBatch)).all())==1
        assert len(db.scalars(select(MembershipConsumptionBill)).all())==1
        assert len(db.scalars(select(MembershipBalanceSnapshot)).all())==1


@pytest.mark.skipif(not os.environ.get("MEMBER_FINANCE_TEST_DATABASE_URL"),reason="isolated PostgreSQL required")
def test_protection_detects_sql_side_effect_and_rolls_back(factory):
    from sqlalchemy import text
    from scripts.member_finance_guard import Protection, snapshot
    with factory() as db:
        baseline=snapshot(db)
    class ChangedProtection(Protection):
        def after(self,db):
            db.execute(text("UPDATE users SET balance_cents=999 WHERE id=1"))
            super().after(db)
    with pytest.raises(ValueError,match="protected_table_changed"):
        imp.execute(factory,packet(),apply=True,protection=ChangedProtection(baseline))
    with factory() as db:
        assert snapshot(db)==baseline


@pytest.mark.skipif(not os.environ.get("MEMBER_FINANCE_TEST_DATABASE_URL"),reason="isolated PostgreSQL required")
def test_protection_accepts_exact_append_and_rejects_stale_baseline(factory):
    from scripts.member_finance_guard import Protection, snapshot
    with factory() as db:
        baseline=snapshot(db)
    guard=Protection(baseline,expected={"membership_consumption_batches":1,"membership_consumption_bills":1,"membership_consumption_lines":1,"membership_balance_snapshots":1})
    assert imp.execute(factory,packet(),apply=True,protection=guard)["status"]=="applied"
    assert guard.result["old_tables_unchanged"] is True
    with pytest.raises(ValueError,match="protection_baseline_changed"):
        imp.execute(factory,packet(),protection=Protection(baseline))


@pytest.mark.skipif(not os.environ.get("MEMBER_FINANCE_TEST_DATABASE_URL"),reason="isolated PostgreSQL required")
def test_protection_wrong_expected_count_rolls_back(factory):
    from scripts.member_finance_guard import Protection,snapshot
    with factory() as db:baseline=snapshot(db)
    expected={name:0 for name in ("membership_consumption_batches","membership_consumption_bills","membership_consumption_lines","membership_balance_snapshots")}
    with pytest.raises(ValueError,match="append_count_mismatch"):
        imp.execute(factory,packet(),apply=True,protection=Protection(baseline,expected=expected))
    with factory() as db:assert snapshot(db)==baseline


def test_decoded_whole_decimal_quantity_stays_visible_after_persistence(factory):
    from decimal import Decimal
    from app.services.customer_consumption import build_customer_consumption_history
    p=packet();source=p.bills[0]
    line=replace(source.bill.lines[0],quantity=Decimal("1"))
    changed=seal(replace(p,bills=(replace(source,bill=replace(source.bill,lines=(line,))),)))
    imp.execute(factory,changed,apply=True)
    with factory() as db:
        history=build_customer_consumption_history(db,db.get(User,1))
        assert history["pagination"]["total"]==1
        assert history["savings"]["amount_cents"]==4000


def test_incremental_acceptance_counts_only_new_rows_and_keeps_old_history(factory, monkeypatch):
    import sys
    from pathlib import Path
    from datetime import timedelta
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/member_sync"))
    from finance_acceptance import expected_counts, verify_projection
    first = packet()
    first = seal(replace(first, bills=(replace(first.bills[0], bill=replace(first.bills[0].bill,
                        refund_status="unknown", payment_evidence_complete=False)),)))
    imp.execute(factory, first, apply=True)
    later = NOW + timedelta(days=1)
    added = replace(first.bills[0], bill=replace(first.bills[0].bill, source_bill_no="SYN-02"))
    second = seal(replace(first, batch_key="synthetic-increment", observed_at=later,
                  bills=(*first.bills, added),
                  balances=(replace(first.balances[0], observed_at=later, total_cents=8000),)))
    preview = imp.execute(factory, second)
    assert expected_counts(preview) == {"membership_consumption_batches":1,
        "membership_consumption_bills":1,"membership_consumption_lines":1,"membership_balance_snapshots":1}
    imp.execute(factory, second, apply=True)
    with factory() as db:
        batch = db.scalar(select(MembershipConsumptionBatch).where(MembershipConsumptionBatch.batch_key==second.batch_key))
        accepted = verify_projection(db, second, batch, preview)
        assert accepted["insert_bills"] == 1
        assert accepted["visible_owned_bills"] == 2
        assert len(db.scalars(select(MembershipBalanceSnapshot)).all()) == 2
        import finance_acceptance
        original = finance_acceptance.build_customer_consumption_history
        def foreign_row(*args, **kwargs):
            value = original(*args, **kwargs)
            value["bills"].append({"id": 999999, "source_bill_no": "FOREIGN"})
            return value
        monkeypatch.setattr(finance_acceptance, "build_customer_consumption_history", foreign_row)
        with pytest.raises(ValueError, match="customer_history_owner_leak"):
            verify_projection(db, second, batch, preview)
        monkeypatch.setattr(finance_acceptance, "build_customer_consumption_history", original)
        with pytest.raises(ValueError, match="actual_count_mismatch"):
            verify_projection(db, second, batch, dict(preview, insert_bills=2))
    with pytest.raises(ValueError, match="preview_count_invalid"):
        expected_counts(dict(preview, insert_bills=True))
    with pytest.raises(ValueError, match="source_revision_conflict"):
        expected_counts(dict(preview, conflicting_bill_groups=1))
