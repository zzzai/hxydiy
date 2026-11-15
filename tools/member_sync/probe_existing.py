"""Print only existing source keys; run inside the API container with a read-only transaction."""
from datetime import datetime, timezone
import json
from sqlalchemy import select, text
from app.models import MembershipCard, Store
from scripts.import_member_cards import SessionLocal

SCOPE = {"tenant_id": 1581452, "shop_id": 1581453, "store_id": 1,
         "source": "meiguanjia_export", "store_code": "hxy-anyang-ziwei-001"}

with SessionLocal() as db:
    db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
    db.execute(text("SET LOCAL statement_timeout = '15s'"))
    if db.scalar(text("SHOW transaction_read_only")) != "on":
        raise RuntimeError("readonly_transaction_required")
    store = db.get(Store, 1)
    if store is None or store.store_code != SCOPE["store_code"]:
        raise RuntimeError("store_identity_mismatch")
    rows = db.execute(select(MembershipCard.store_id, MembershipCard.source_card_key)
                      .where(MembershipCard.source == SCOPE["source"])).all()
    if any(row.store_id != 1 for row in rows):
        raise RuntimeError("source_store_conflict")
    keys = sorted(row.source_card_key for row in rows)
    if len(keys) != len(set(keys)) or not keys:
        raise RuntimeError("invalid_existing_keyset")
    db.rollback()
print(json.dumps({"scope": SCOPE, "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                  "source_keys": keys, "source_cards": len(keys), "business_writes": 0, "transaction_read_only": True},
                 sort_keys=True))
