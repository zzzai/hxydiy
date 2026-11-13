from app.domain.member_consumption import BillLine, ConsumptionBill, aggregate_verified, compute_bill_savings, ingest_bills, visible_to


def line(price, settled, qty=1, desc="合成项目"):
    return BillLine(desc, qty, price, settled)


def bill(**overrides):
    base = dict(
        source_bill_no="SYN-001", source_row_sha256="sha-1", store_id=1, user_id=11,
        lines=(line(30000, 24000),), store_price_total_cents=30000, settled_total_cents=24000,
        card_principal_debit_cents=15000, coupon_payment_cents=9000,
    )
    base.update(overrides)
    return ConsumptionBill(**base)


def test_verified_savings_excludes_card_and_coupon_payments():
    result = compute_bill_savings(bill())
    assert result.status == "verified"
    assert result.savings_cents == 6000  # 300 - 240; coupon 90 and card 150 are payments
    assert result.coupon_payment_cents == 9000
    assert result.card_payment_cents == 15000


def test_simple_119_79_example_is_40_not_119():
    result = compute_bill_savings(bill(lines=(line(11900, 7900),), store_price_total_cents=11900,
                                      settled_total_cents=7900, card_principal_debit_cents=7900,
                                      coupon_payment_cents=0))
    assert result.status == "verified" and result.savings_cents == 4000


def test_open_card_recharge_and_shared_are_not_consumption_savings():
    assert compute_bill_savings(bill(bill_type="open_card")).status == "excluded"
    assert compute_bill_savings(bill(bill_type="recharge")).status == "excluded"
    assert compute_bill_savings(bill(attribution_status="shared")).status == "blocked"
    assert compute_bill_savings(bill(refund_status="unknown")).status == "blocked"


def test_missing_price_or_payment_is_unknown_not_zero():
    assert compute_bill_savings(bill(settled_total_cents=None)).status == "unknown"
    assert compute_bill_savings(bill(lines=(BillLine("合成", 1, None, 100),))).status == "unknown"
    assert compute_bill_savings(bill(store_price_total_cents=99999)).status == "anomaly"


def test_duplicate_and_changed_bill_are_idempotent_or_conflict():
    existing = {}
    first = bill()
    assert ingest_bills(existing, [first]) == {"inserted": ["SYN-001"], "duplicates": [], "conflicts": []}
    assert ingest_bills(existing, [first]) == {"inserted": [], "duplicates": ["SYN-001"], "conflicts": []}
    changed = bill(source_row_sha256="sha-2", settled_total_cents=23000, lines=(line(30000, 23000),))
    assert ingest_bills(existing, [changed]) == {"inserted": [], "duplicates": [], "conflicts": ["SYN-001"]}
    assert existing[(1, "SYN-001")] == "sha-1"


def test_multi_card_and_multi_person_bill_counts_once():
    shared = bill(linked_card_ids=(1, 2), source_bill_no="SYN-MULTI")
    own = bill(source_bill_no="SYN-OWN")
    result = aggregate_verified([shared, shared, own, own])
    assert result["unique_bills"] == 2
    assert result["verified_bills"] == 2
    assert result["savings_cents"] == 12000


def test_account_and_store_isolation():
    own = bill()
    assert visible_to(own, 11, 1) is True
    assert visible_to(own, 12, 1) is False
    assert visible_to(own, 11, 2) is False
