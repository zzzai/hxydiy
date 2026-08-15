"""Create or reset the first store-bound DIY administrator.

The script refuses to guess when the database does not contain exactly one
store. Credentials are written by the caller to a root-only host path.
"""

import os
import secrets
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.admin import hash_password
from app.db.session import SessionLocal
from app.models import Staff, Store


def setup_admin(db: Session, password: str | None = None) -> str:
    stores = list(db.scalars(select(Store).order_by(Store.id)))
    if len(stores) != 1:
        raise RuntimeError("初始化管理员要求数据库中恰好存在一个唯一门店")
    password = password or secrets.token_urlsafe(12)
    staff = db.scalar(select(Staff).where(Staff.username == "admin"))
    if staff is None:
        staff = Staff(username="admin", name="店长")
        db.add(staff)
    staff.password_hash = hash_password(password)
    staff.role = "admin"
    staff.status = "active"
    staff.store_id = stores[0].id
    db.commit()
    return password


def write_credentials(credentials_path: Path, username: str, password: str) -> None:
    descriptor = os.open(credentials_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as credentials:
        credentials.write(f"username: {username}\npassword: {password}\n")


def main() -> None:
    with SessionLocal() as db:
        password = setup_admin(db)
    credentials_path = Path(os.environ.get("ADMIN_CREDENTIALS_PATH", "/tmp/admin-credentials.txt"))
    write_credentials(credentials_path, "admin", password)
    print("ADMIN_SETUP_DONE")


if __name__ == "__main__":
    main()
