from app.domain.member_consumption import BillLine, ConsumptionBill, aggregate_verified, bill_content_sha256, compute_bill_savings, ingest_bills, visible_to


def line(price, settled, qty=1, desc="合成项目"):
    return BillLine(desc, qty, price, settled)


def bill(**overrides):
    base = dict(
        source_bill_no="SYN-001", source_row_sha256="sha-1", store_id=1, user_id=11,
        bill_type="service", bill_status="normal_settled", attribution_status="owned", refund_status="none",
        payment_evidence_complete=True,
        lines=(line(30000, 24000),), store_price_total_cents=30000, settled_total_cents=24000,
        card_principal_debit_cents=15000, card_bonus_debit_cents=0, coupon_payment_cents=9000,
        cash_payment_cents=0, other_payment_cents=0,
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
                                      card_bonus_debit_cents=0, coupon_payment_cents=0,
                                      cash_payment_cents=0, other_payment_cents=0))
    assert result.status == "verified" and result.savings_cents == 4000


def test_payment_breakdown_must_be_complete_and_reconcile():
    assert compute_bill_savings(bill(payment_evidence_complete=False)).status == "unknown"
    assert compute_bill_savings(bill(card_bonus_debit_cents=None)).status == "unknown"
    assert compute_bill_savings(bill(cash_payment_cents=None)).status == "unknown"
    # 1 cent of known payment cannot be trusted against a 240.00 settlement.
    incomplete = bill(card_principal_debit_cents=1, card_bonus_debit_cents=0,
                      coupon_payment_cents=0, cash_payment_cents=0, other_payment_cents=0)
    assert compute_bill_savings(incomplete).status == "anomaly"
    mismatch = bill(card_principal_debit_cents=14000, card_bonus_debit_cents=0,
                    coupon_payment_cents=9000, cash_payment_cents=0, other_payment_cents=0)
    assert compute_bill_savings(mismatch).status == "anomaly"


def test_negative_settlement_and_negative_savings_are_blocked():
    negative = bill(settled_total_cents=-1000, lines=(line(30000, -1000),),
                    card_principal_debit_cents=-1000, card_bonus_debit_cents=0,
                    coupon_payment_cents=0, cash_payment_cents=0, other_payment_cents=0)
    assert compute_bill_savings(negative).status == "anomaly"
    overpaid = bill(settled_total_cents=31000, lines=(line(30000, 31000),),
                    card_principal_debit_cents=31000, card_bonus_debit_cents=0,
                    coupon_payment_cents=0, cash_payment_cents=0, other_payment_cents=0)
    assert compute_bill_savings(overpaid).status == "anomaly"


def test_defaults_are_unknown_not_verified():
    bare = ConsumptionBill(source_bill_no="UNKNOWN", source_row_sha256="sha", store_id=1, user_id=11)
    assert bare.bill_type == "unknown"
    assert bare.bill_status == "unknown"
    assert bare.attribution_status == "unresolved"
    assert bare.refund_status == "unknown"
    assert compute_bill_savings(bare).status == "excluded"
    assert compute_bill_savings(bill(bill_status="unknown")).status == "blocked"
    assert compute_bill_savings(bill(bill_status="voided")).status == "blocked"
    assert compute_bill_savings(bill(attribution_status="unresolved")).status == "blocked"
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
    changed = bill(source_row_sha256="sha-2", settled_total_cents=23000, lines=(line(30000, 23000),),
                   card_principal_debit_cents=14000, card_bonus_debit_cents=0,
                   coupon_payment_cents=9000, cash_payment_cents=0, other_payment_cents=0)
    assert ingest_bills(existing, [changed]) == {"inserted": [], "duplicates": [], "conflicts": ["SYN-001"]}
    assert existing[(1, "SYN-001")] == bill_content_sha256(first)


def test_conflicting_versions_exclude_group_and_ignore_input_order():
    v1 = bill(source_bill_no="SYN-VERSION", source_row_sha256="v1", source_bill_version="v1",
              bill_status="voided")
    v2 = bill(source_bill_no="SYN-VERSION", source_row_sha256="v2", source_bill_version="v2",
              refund_status="unknown", payment_evidence_complete=False)
    for order in ([v1, v2], [v2, v1]):
        result = aggregate_verified(order)
        assert result["savings_cents"] is None
        assert result["verified_bills"] == 0
        assert result["conflict_bills"] == 1 and result["blocked_bills"] == 1


def test_no_verified_bills_returns_null_not_zero():
    result = aggregate_verified([bill(source_bill_no="SYN-RECHARGE", bill_type="recharge"),
                                 bill(source_bill_no="SYN-REFUND-UNKNOWN", refund_status="unknown")])
    assert result["savings_cents"] is None
    assert result["verified_bills"] == 0


def test_voided_positive_amounts_never_count_as_verified_consumption():
    voided = bill(source_bill_no="SYN-VOID", source_row_sha256="void-1", bill_status="voided",
                  source_bill_version="1")
    # The source keeps original/paid amounts positive for voided/re-recorded versions.
    assert voided.settled_total_cents > 0
    assert compute_bill_savings(voided).status == "blocked"
    assert aggregate_verified([voided])["savings_cents"] is None


def test_multi_card_and_multi_person_bill_counts_once():
    multi_card = bill(source_bill_no="SYN-MULTI", linked_card_ids=(1, 2))
    own = bill(source_bill_no="SYN-OWN")
    result = aggregate_verified([multi_card, multi_card, own, own])
    assert result["unique_bills"] == 2
    assert result["verified_bills"] == 2
    assert result["savings_cents"] == 12000
    shared = bill(source_bill_no="SYN-SHARED", attribution_status="shared")
    blocked = aggregate_verified([own, shared])
    assert blocked["savings_cents"] == 6000
    assert blocked["verified_bills"] == 1 and blocked["blocked_bills"] == 1


def test_account_and_store_isolation_rejects_unresolved_shared():
    own = bill()
    assert visible_to(own, 11, 1) is True
    assert visible_to(own, 12, 1) is False
    assert visible_to(own, 11, 2) is False
    assert visible_to(bill(attribution_status="unresolved"), 11, 1) is False
    assert visible_to(bill(attribution_status="shared"), 11, 1) is False
    assert visible_to(bill(user_id=None), 11, 1) is False
    assert visible_to(bill(attribution_status="unknown"), 11, 1) is False


def test_same_batch_same_bill_conflict_zero_partial_write():
    v1 = bill(source_bill_no="SYN-VERSION", source_row_sha256="v1", source_bill_version="v1",
              bill_status="voided")
    v2 = bill(source_bill_no="SYN-VERSION", source_row_sha256="v2", source_bill_version="v2",
              refund_status="unknown", payment_evidence_complete=False)
    for order in ([v1, v2], [v2, v1]):
        existing = {}
        result = ingest_bills(existing, order)
        assert result == {"inserted": [], "duplicates": [], "conflicts": ["SYN-VERSION"]}
        assert existing == {}


def test_mixed_batch_accepts_only_clean_groups():
    clean = bill(source_bill_no="SYN-CLEAN")
    v1 = bill(source_bill_no="SYN-VERSION", source_row_sha256="v1", bill_status="voided")
    v2 = bill(source_bill_no="SYN-VERSION", source_row_sha256="v2", refund_status="unknown",
              payment_evidence_complete=False)
    existing = {}
    result = ingest_bills(existing, [clean, v1, v2])
    assert result["inserted"] == ["SYN-CLEAN"]
    assert result["conflicts"] == ["SYN-VERSION"]
    assert existing == {(1, "SYN-CLEAN"): bill_content_sha256(clean)}

    existing2 = {}
    result2 = ingest_bills(existing2, [v2, v1, clean])
    assert result2["inserted"] == ["SYN-CLEAN"]
    assert result2["conflicts"] == ["SYN-VERSION"]
    assert existing2 == {(1, "SYN-CLEAN"): bill_content_sha256(clean)}


def test_existing_entries_preserved_on_conflict():
    first = bill()
    existing = {}
    ingest_bills(existing, [first])
    before = dict(existing)
    changed = bill(source_row_sha256="sha-2", settled_total_cents=23000, lines=(line(30000, 23000),),
                   card_principal_debit_cents=14000, card_bonus_debit_cents=0,
                   coupon_payment_cents=9000, cash_payment_cents=0, other_payment_cents=0)
    result = ingest_bills(existing, [changed])
    assert result["conflicts"] == ["SYN-001"]
    assert existing == before


def test_same_evidence_hash_different_content_is_conflict():
    base = bill(source_bill_no="SYN-FORGED", source_row_sha256="same-hash")
    different_refund = bill(source_bill_no="SYN-FORGED", source_row_sha256="same-hash", refund_status="refunded")
    different_amount = bill(source_bill_no="SYN-FORGED", source_row_sha256="same-hash",
                            settled_total_cents=23000, lines=(line(30000, 23000),),
                            card_principal_debit_cents=14000, card_bonus_debit_cents=0,
                            coupon_payment_cents=9000, cash_payment_cents=0, other_payment_cents=0)
    different_attribution = bill(source_bill_no="SYN-FORGED", source_row_sha256="same-hash",
                                 attribution_status="shared")
    for other in (different_refund, different_amount, different_attribution):
        for order in ([base, other], [other, base]):
            result = aggregate_verified(order)
            assert result["savings_cents"] is None
            assert result["verified_bills"] == 0
            assert result["conflict_bills"] == 1
            assert result["blocked_bills"] == 1


def test_same_evidence_hash_different_content_conflicts_in_ingest():
    a = bill(source_bill_no="SYN-FORGED-INGEST", source_row_sha256="same-hash")
    b = bill(source_bill_no="SYN-FORGED-INGEST", source_row_sha256="same-hash", refund_status="refunded")
    existing = {}
    result = ingest_bills(existing, [a, b])
    assert result["conflicts"] == ["SYN-FORGED-INGEST"]
    assert existing == {}


def test_duplicate_identical_service_lines_preserved_in_semantic_key():
    one = bill(source_bill_no="SYN-LINES", lines=(line(11900, 7900),), store_price_total_cents=11900,
               settled_total_cents=7900, card_principal_debit_cents=7900, card_bonus_debit_cents=0,
               coupon_payment_cents=0, cash_payment_cents=0, other_payment_cents=0)
    two = bill(source_bill_no="SYN-LINES", lines=(line(11900, 7900), line(11900, 7900)),
               store_price_total_cents=23800, settled_total_cents=15800,
               card_principal_debit_cents=15800, card_bonus_debit_cents=0,
               coupon_payment_cents=0, cash_payment_cents=0, other_payment_cents=0)
    assert bill_content_sha256(one) != bill_content_sha256(two)

def test_foreign_currency_is_unknown_not_verified():
    usd = bill(source_bill_no="SYN-USD", currency="USD")
    result = compute_bill_savings(usd)
    assert result.status == "unknown"
    assert "currency" in result.reason
    assert aggregate_verified([usd])["savings_cents"] is None
