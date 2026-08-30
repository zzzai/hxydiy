# -*- coding: utf-8 -*-
"""补营销券字段+补种模板。用法: docker exec -e PYTHONPATH=/app hxy-api python /tmp/setup_marketing.py"""
from sqlalchemy import text

from app.db.session import SessionLocal, engine
from app.models import CouponTemplate
from app.seed import MARKETING_COUPONS

# 1. 加列
with engine.begin() as conn:
    for ddl in (
        "ALTER TABLE coupon_templates ADD COLUMN IF NOT EXISTS is_claimable BOOLEAN DEFAULT FALSE",
        "ALTER TABLE coupon_templates ADD COLUMN IF NOT EXISTS claim_limit INTEGER DEFAULT 1",
        "ALTER TABLE coupon_templates ADD COLUMN IF NOT EXISTS daily_claimable BOOLEAN DEFAULT FALSE",
    ):
        conn.execute(text(ddl))
print("COLUMNS_OK")

# 2. 补种模板
db = SessionLocal()
n = 0
for m in MARKETING_COUPONS:
    if db.query(CouponTemplate).filter(CouponTemplate.code == m["code"]).first():
        continue
    db.add(CouponTemplate(**m, status="published"))
    n += 1
db.commit()
db.close()
print(f"SEEDED {n}")
