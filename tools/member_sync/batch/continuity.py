"""Preserve every prior row; the bootstrap exception is bound to one approved snapshot."""
import hashlib
import json
from datetime import datetime
from sqlalchemy import select

BOOTSTRAP_AUTH_SHA = "a2146d556bd83707665b31bdb9b91534db9e2dc2b2da4f381093a3f901e6db0a"


def read(root, name, expected=None):
    content = (root / name).read_bytes()
    if expected is not None:
        assert hashlib.sha256(content).hexdigest() == expected, "continuity_evidence_hash"
    return json.loads(content)


def same_rows(state, expected):
    for table, key in [("users", "user_id"), ("cards", "card_id")]:
        actual = {r[key]: r["full_row_sha256"] for r in state[table]}
        assert all(actual.get(r[key]) == r["full_row_sha256"] for r in expected[table]), "prior_records_changed"
    assert len(state["cards"]) == len(expected["cards"]), "unexpected_prior_cards"


def verify_continuity(db, guard, root, request, state, phones, new_keys):
    prior = read(root, "prior-protection-private.json", request["prior_protection_sha256"])
    previous_input = read(root, "prior-input-private.json", request["prior_input_sha256"])
    receipt = db.scalars(select(guard.AuditLog).where(
        guard.AuditLog.action == "member_card_batch_applied", guard.AuditLog.store_id == 1,
        guard.AuditLog.detail["manifest_sha256"].as_string() == request["prior_manifest_sha256"])).one().detail
    assert receipt["input_sha256"] == request["prior_input_sha256"]
    assert receipt["runner_sha256"] == request["runner_sha256"]
    card_ids = []
    for row in previous_input["cards"]:
        card = db.scalars(select(guard.MembershipCard).where(
            guard.MembershipCard.source == guard.SOURCE,
            guard.MembershipCard.source_card_key == guard.source_key(row["source_card_id"]))).one()
        assert db.get(guard.User, card.user_id).phone == row["phone"] and card.store_id == 1
        assert card.status == row["status"] == "active"
        assert card.card_type == ("annual" if row["card_name"] == "荷小悦年度权益会员卡" else "stored")
        assert card.balance_cents == row["balance_cents"]
        assert card.started_at == datetime.fromisoformat(row["started_at"])
        assert card.expires_at == (datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None)
        card_ids.append(card.id)
    assert set(card_ids) == set(receipt["card_ids"]), "prior_audit_cards_changed"
    original_ids = {r["user_id"] for r in prior["protected_users"]["rows"]} | set(receipt["user_ids"])
    if request["continuity_mode"] == "approved_20261113_snapshot":
        auth = read(root, "bootstrap-authority.json", BOOTSTRAP_AUTH_SHA)
        initial = read(root, "bootstrap-initial-private.json", auth["authorized_initial_evidence_sha256"])
        differences = read(root, "bootstrap-differences-private.json", auth["authorized_difference_sha256"])
        facts = read(root, "bootstrap-source-private.json", auth["source_facts_sha256"])
        match = read(root, "bootstrap-match-summary.json", auth["candidate_match_sha256"])
        assert initial["state"]["sha256"] == auth["authorized_state_sha256"]
        assert auth["scope_does_not_cover_new_unverified_differences"] is True
        assert initial["differences"]["cards"] == [] and len(differences) == 2
        assert {r["user_id"] for r in differences} == set(initial["differences"]["users"])
        assert all(set(r["changed_columns"]) == {"customer_login_version", "last_login_at"} for r in differences)
        same_rows(state, initial["state"])
        # All old approved candidates must still be new and match their original identity and dates.
        current = {r["phone"]: r for r in read(root, "source-ui-facts-private.json")["rows"] if "phone" in r}
        approved = [r for r in facts["rows"] if "phone" in r]
        assert len(approved) == 15 and match["existing_user_matches"] == 1
        for row in approved:
            assert guard.source_key(row["card_number"]) in new_keys
            now = current.get(row["phone"])
            assert now and all(now[k] == row[k] for k in ["card_number", "phone", "card_name", "opened_at_date", "expires_at_date"])
        approved_phones = {r["phone"] for r in approved}
        allowed_matches = db.execute(select(guard.User.id, guard.User.phone).where(guard.User.phone.in_(approved_phones))).all()
        assert len(allowed_matches) == 1 and allowed_matches[0].id in {r["user_id"] for r in initial["state"]["users"]}
        permitted_ids = original_ids | {allowed_matches[0].id}
        protected_count = len(initial["state"]["users"])
    elif request["continuity_mode"] == "previous_success":
        guard.check_original_records(state, prior, exact=False)
        assert len(state["cards"]) == len(prior["protected_cards"]["global_rows"])
        permitted_ids = original_ids
        protected_count = len(prior["protected_users"]["rows"])
    else:
        raise ValueError("unknown_continuity_mode")
    matches = db.execute(select(guard.User.id, guard.User.phone).where(guard.User.phone.in_(phones))).all()
    assert len(matches) == len({r.phone for r in matches}), "ambiguous_phone_owner"
    assert all(r.id in permitted_ids for r in matches), "new_registration_candidate_overlap"
    return {"status": "passed", "protected_prior_users": protected_count,
            "prior_inserted_cards_verified": len(card_ids), "prior_audit_count": 1,
            "existing_user_matches": len(matches), "unexpected_account_changes": 0,
            "current_protected_users": len(state["users"]), "current_protected_cards": len(state["cards"]),
            "business_writes": 0, "continuity_mode": request["continuity_mode"]}
