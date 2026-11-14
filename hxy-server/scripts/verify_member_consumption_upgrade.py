"""Isolated prior-schema-to-new Alembic acceptance for the member consumption migration.

Runs only against a disposable PostgreSQL database provided via DATABASE_URL.
Never production. Proves: baseline without the four candidate tables upgrades,
empty downgrade + re-upgrade, non-empty downgrade refusal, old baseline rows unchanged.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import MetaData, create_engine, inspect, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import models  # noqa: F401
from app.db.session import Base

URL = os.environ["DATABASE_URL"]
parsed = make_url(URL)
assert parsed.database == "test", "disposable test database required"

NEW_TABLES = {
    "membership_consumption_batches",
    "membership_consumption_bills",
    "membership_consumption_lines",
    "membership_balance_snapshots",
}
PREDECESSOR = "20261112_coupon_poster_links"

report = {"ok": False, "steps": []}


def alembic(*args):
    env = os.environ.copy()
    env["DATABASE_URL"] = URL
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT, env=env,
                          capture_output=True, text=True)


def tables():
    return set(inspect(engine).get_table_names())


engine = create_engine(URL)

previous = MetaData()
for table in Base.metadata.tables.values():
    if table.name in NEW_TABLES:
        continue
    table.to_metadata(previous)
previous.create_all(engine)

before = tables()
assert not (NEW_TABLES & before), "candidate tables present before upgrade"
report["steps"].append({"step": "baseline_without_candidate_tables", "ok": True})

with engine.begin() as conn:
    conn.execute(text("INSERT INTO stores (store_code, name, city, address, phone, business_hours, status) VALUES ('mc-baseline', 'Baseline', '', 'Synthetic', '', '', 'open')"))
    old_row = dict(conn.execute(text("SELECT store_code, name, city, address, status FROM stores WHERE store_code = 'mc-baseline'")).mappings().first())
report["steps"].append({"step": "old_baseline_row_inserted", "ok": bool(old_row)})

stamp = alembic("stamp", PREDECESSOR)
assert stamp.returncode == 0, stamp.stderr
upgrade = alembic("upgrade", "head")
assert upgrade.returncode == 0, upgrade.stderr
after = tables()
assert NEW_TABLES <= after, "upgrade did not create candidate tables"

inspector = inspect(engine)
def cols(name):
    return {c["name"] for c in inspector.get_columns(name)}
def uniques(name):
    return {tuple(c["column_names"]) for c in inspector.get_unique_constraints(name)}
def indexes(name):
    return {i["name"] for i in inspector.get_indexes(name)}
checks = {
    "batches_columns": {"source", "store_id", "batch_key", "status", "observed_at", "coverage_gaps", "last_page_complete", "page_count"} <= cols("membership_consumption_batches"),
    "bills_columns": {"source", "store_id", "source_bill_no", "content_sha256", "occurred_at", "settled_at", "source_version_no", "source_current_marker", "currency"} <= cols("membership_consumption_bills"),
    "lines_columns": {"bill_id", "quantity", "store_price_cents", "settled_cents", "line_order", "description"} <= cols("membership_consumption_lines"),
    "snapshots_columns": {"card_id", "observed_at", "source_batch_id", "total_cents", "principal_cents", "bonus_cents"} <= cols("membership_balance_snapshots"),
    "batches_unique": ("source", "store_id", "batch_key") in uniques("membership_consumption_batches"),
    "bills_unique": ("source", "store_id", "source_bill_no", "content_sha256") in uniques("membership_consumption_bills"),
    "snapshots_unique": ("card_id", "observed_at", "source_batch_id") in uniques("membership_balance_snapshots"),
    "batches_index": "ix_membership_consumption_batches_store_id" in indexes("membership_consumption_batches"),
    "lines_index": "ix_member_consumption_line_bill" in indexes("membership_consumption_lines"),
    "snapshots_index": "ix_membership_balance_snapshots_card_id" in indexes("membership_balance_snapshots"),
}
assert all(checks.values()), {k: v for k, v in checks.items() if not v}
report["steps"].append({"step": "upgrade_created_tables_constraints_indexes", "ok": True})

with engine.connect() as conn:
    row = dict(conn.execute(text("SELECT store_code, name, city, address, status FROM stores WHERE store_code = 'mc-baseline'")).mappings().first())
assert row == old_row, "old baseline row changed after upgrade"
report["steps"].append({"step": "old_baseline_row_unchanged_after_upgrade", "ok": True})

down = alembic("downgrade", PREDECESSOR)
assert down.returncode == 0, down.stderr
assert not (NEW_TABLES & tables()), "downgrade did not drop empty candidate tables"
report["steps"].append({"step": "empty_downgrade_dropped_tables", "ok": True})

re_up = alembic("upgrade", "head")
assert re_up.returncode == 0, re_up.stderr
assert NEW_TABLES <= tables(), "re-upgrade failed"
report["steps"].append({"step": "re_upgrade_ok", "ok": True})

with engine.begin() as conn:
    store_id = conn.execute(text("SELECT id FROM stores WHERE store_code = 'mc-baseline'")).scalar_one()
    conn.execute(text(
        "INSERT INTO membership_consumption_batches (source, store_id, batch_key, source_snapshot_sha256, manifest_sha256, query_range_start, query_range_end, observed_at, status, evidence_ref) "
        "VALUES ('meiguanjia_export', :store_id, 'refuse-test', 's', 'm', now(), now(), now(), 'applied', 'synthetic')"
    ), {"store_id": store_id})

refuse = alembic("downgrade", PREDECESSOR)
assert refuse.returncode != 0, "downgrade must refuse a non-empty table"
assert "has rows" in refuse.stderr, refuse.stderr
assert NEW_TABLES <= tables(), "refused downgrade must not drop tables"
with engine.connect() as conn:
    n = conn.execute(text("SELECT count(*) FROM membership_consumption_batches")).scalar_one()
assert n == 1, "batches row must remain after refused downgrade"
report["steps"].append({"step": "nonempty_downgrade_refused_rows_kept", "ok": True, "stderr": refuse.stderr.strip()[:300]})

report["ok"] = True
report["predecessor"] = PREDECESSOR
report["head"] = "20261114_member_consumption"
print(json.dumps(report, ensure_ascii=False, indent=2))
