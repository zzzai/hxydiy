"""幂等初始化门店技师画像快记标签。

用法：python scripts/seed_profile_tags.py --store-id 1
默认只读预览；传 --apply 才写入数据库。
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import AuditLog, CustomerTag, Store


PROFILE_TAGS = (
    ("年龄段·18-25岁", "#5b8ff9"),
    ("年龄段·26-35岁", "#5b8ff9"),
    ("年龄段·36-45岁", "#5b8ff9"),
    ("年龄段·46岁以上", "#5b8ff9"),
    ("性别·男", "#7b61ff"),
    ("性别·女", "#7b61ff"),
    ("体型·偏瘦", "#61a0a8"),
    ("体型·标准", "#61a0a8"),
    ("体型·偏壮", "#61a0a8"),
    ("职业·久坐", "#36a2a2"),
    ("职业·久站", "#36a2a2"),
    ("职业·体力工作", "#36a2a2"),
    ("肩颈紧张", "#f08c46"),
    ("腰部不适", "#f08c46"),
    ("腿部酸胀", "#f08c46"),
    ("局部硬结", "#f08c46"),
    ("偏好轻柔力度", "#52a675"),
    ("偏好中等力度", "#52a675"),
    ("偏好强力力度", "#52a675"),
    ("首次到店", "#9b7ede"),
    ("重点维护", "#d85b6a"),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store-id", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        store = db.scalar(select(Store).where(Store.id == args.store_id))
        if not store:
            raise SystemExit(f"store {args.store_id} not found")
        existing = {
            tag.name
            for tag in db.scalars(select(CustomerTag).where(CustomerTag.store_id == args.store_id))
        }
        missing = [(name, color) for name, color in PROFILE_TAGS if name not in existing]
        print(f"store={store.id} {store.name}; existing={len(existing)} missing={len(missing)}")
        for name, _ in missing:
            print(f"- {name}")
        if not args.apply or not missing:
            return
        for name, color in missing:
            db.add(CustomerTag(store_id=args.store_id, name=name, color=color, tag_type="profile", description="技师画像快记"))
        db.add(AuditLog(actor_type="system", actor_id="seed_profile_tags", store_id=args.store_id, action="profile_tags_seeded", entity_type="customer_tags", entity_id=str(args.store_id), detail={"count": len(missing), "names": [name for name, _ in missing]}))
        db.commit()
        print(f"created={len(missing)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
