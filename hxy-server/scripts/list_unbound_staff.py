"""盘点迁移前未绑定技师档案的历史 staff 账号。"""

import json

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Staff


def list_unbound() -> list[dict]:
    with SessionLocal() as db:
        rows = db.scalars(
            select(Staff).where(Staff.role == "staff", Staff.technician_id.is_(None)).order_by(Staff.id)
        ).all()
        return [{"id": row.id, "username": row.username, "name": row.name, "store_id": row.store_id} for row in rows]


if __name__ == "__main__":
    print(json.dumps(list_unbound(), ensure_ascii=False, indent=2))
