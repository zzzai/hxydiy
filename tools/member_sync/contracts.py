"""Validate source evidence without access to a database or an importer."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

SCOPE = {"tenant_id": 1581452, "shop_id": 1581453, "store_id": 1,
         "source": "meiguanjia_export", "store_code": "hxy-anyang-ziwei-001"}
SHOP = "紫薇壹号店"
CARD_NAMES = {"荷小悦年度权益会员卡", "荷小悦会员卡"}
BAD_STATE = re.compile("停用|退卡|挂失|注销|冻结")
SHA = re.compile(r"[a-f0-9]{64}")
TZ = timezone(timedelta(hours=8))


class Stop(ValueError):
    """A fixed diagnostic code, never a customer value."""


def require(condition, code):
    if not condition:
        raise Stop(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def source_key(raw):
    require(type(raw) is str and bool(raw.strip()), "invalid_raw_card_number")
    # Preserve all characters, including leading zeros and whitespace.
    return hashlib.sha256((SCOPE["store_code"] + "\0" + raw).encode()).hexdigest()


def money(value):
    try:
        require(type(value) is str and re.fullmatch(r"\d+(?:\.\d{1,2})?", value),
                "invalid_source_amount")
        cents = Decimal(value) * 100
        require(cents.is_finite() and 0 <= cents <= 2**31 - 1, "invalid_source_amount")
        return int(cents)
    except (InvalidOperation, TypeError):
        raise Stop("invalid_source_amount") from None


def date_only(value):
    require(type(value) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value),
            "invalid_source_date")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise Stop("invalid_source_date") from None


def index_keys(index, now):
    require(index.get("scope") == SCOPE and index.get("business_writes") == 0,
            "index_scope_mismatch")
    try:
        observed = datetime.fromisoformat(index["observed_at_utc"])
        age = (now - observed).total_seconds()
    except (KeyError, TypeError, ValueError):
        raise Stop("invalid_index_time") from None
    require(observed.tzinfo is not None and 0 <= age <= 1800, "stale_index")
    keys = index.get("source_keys")
    require(type(keys) is list and all(type(k) is str and SHA.fullmatch(k) for k in keys),
            "invalid_index_keys")
    require(len(set(keys)) == len(keys) and index.get("source_cards") == len(keys),
            "duplicate_index_keys")
    # This installation already has cards. An empty index must not turn every row into new.
    require(len(keys) > 0, "empty_existing_index")
    return set(keys)


def flatten_pass(observation):
    require(observation.get("scope") == SCOPE, "source_scope_mismatch")
    require(observation.get("search_text") == "" and observation.get("shop_name") == SHOP,
            "source_filter_mismatch")
    total, pages = observation.get("total"), observation.get("pages")
    require(type(total) is int and 0 < total <= 10000, "invalid_source_total")
    require(type(pages) is list and len(pages) == (total + 14) // 15, "incomplete_pages")
    rows = []
    for number, page in enumerate(pages, 1):
        expected = min(15, total - (number - 1) * 15)
        require(page.get("number") == number and page.get("total") == total,
                "page_sequence_changed")
        require(type(page.get("rows")) is list and len(page["rows"]) == expected,
                "incomplete_page_rows")
        for row in page["rows"]:
            require(row.get("store_name") == SHOP and row.get("allow_cross_store_text") == "否",
                    "source_store_conflict")
            require(not BAD_STATE.search(row.get("state_text", "")), "source_adverse_state")
            source_key(row.get("card_number"))
            rows.append(row)
    require(len({source_key(r["card_number"]) for r in rows}) == total, "duplicate_source_key")
    return rows


def candidate(row, detail):
    require(row.get("card_name") in CARD_NAMES and row.get("source_card_type") == "储值消费卡",
            "unsupported_candidate_card")
    require(detail.get("card_number") == row["card_number"]
            and detail.get("card_name") == row["card_name"]
            and detail.get("store_name") == SHOP, "candidate_ownership_conflict")
    phone = detail.get("phone")
    require(type(phone) is str and re.fullmatch(r"1[3-9]\d{9}", phone), "invalid_full_phone")
    require(row.get("masked_phone") == phone[:3] + "****" + phone[-4:],
            "candidate_phone_mismatch")
    require(not BAD_STATE.search(detail.get("state_text", "")), "candidate_adverse_state")
    opened = date_only(row.get("opened_at_date"))
    require(detail.get("opened_at_date") == row["opened_at_date"], "candidate_open_date_mismatch")
    expiry = row.get("expires_at_date")
    if expiry:
        require(date_only(expiry) >= opened and detail.get("expiry_text") == expiry,
                "candidate_expiry_mismatch")
    else:
        require(row["card_name"] == "荷小悦会员卡" and detail.get("expiry_text") == "不限期",
                "candidate_unlimited_not_proven")
    balance = money(row.get("balance_yuan"))
    require(balance == money(detail.get("balance_yuan")), "candidate_balance_changed")
    return {"card_number": row["card_number"], "source_key": source_key(row["card_number"]),
            "phone": phone, "card_name": row["card_name"], "source_card_type": row["source_card_type"],
            "store_name": SHOP, "masked_phone": row["masked_phone"], "balance_cents": balance,
            "opened_at_date": row["opened_at_date"], "expires_at_date": expiry or None,
            "source_expiry_unlimited": not bool(expiry), "date_precision": "date_only",
            "timezone": "UTC+08:00", "allow_cross_store_text": "否"}


def verify(index, passes, now=None):
    now = now or datetime.now(timezone.utc)
    known = index_keys(index, now)
    require(type(passes) is list and len(passes) == 2, "two_complete_passes_required")
    rows = [flatten_pass(p) for p in passes]
    maps = [{source_key(r["card_number"]): r for r in scan} for scan in rows]
    require(maps[0].keys() == maps[1].keys(), "source_keyset_changed")
    new_keys = sorted(maps[0].keys() - known)
    for observation in passes:
        require(type(observation.get("details")) is dict
                and set(observation["details"]) == set(new_keys), "candidate_details_scope_mismatch")
    validated = []
    for key in new_keys:
        values = []
        for pass_no in (0, 1):
            details = passes[pass_no].get("details", {})
            require(key in details, "candidate_detail_missing")
            values.append(candidate(maps[pass_no][key], details[key]))
        require(values[0] == values[1], "candidate_changed_between_passes")
        validated.append(values[0])
    keyset_sha = hashlib.sha256("\n".join(sorted(maps[0])).encode()).hexdigest()
    return {"version": 1, "status": "readonly_passed" if new_keys else "no_new",
            "scope": SCOPE, "verified_at_utc": now.isoformat(),
            "source_keyset_sha256": keyset_sha, "index_sha256": digest(index),
            "source_evidence_sha256": digest(passes), "source_cards": len(maps[0]),
            "new_cards": len(validated), "candidate_people": len({r["phone"] for r in validated}),
            "existing_source_cards_missing": len(known - maps[0].keys()),
            "standing_confirmation_date": "2026-10-25",
            "confirmation_basis": "standing_confirmation_bound_to_this_snapshot",
            "business_writes": 0, "apply_enabled": False, "candidates": validated}
