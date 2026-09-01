"""Create store-bound DIY staff accounts in a single-store deployment.

Usage:
  python scripts/setup_staff.py <username> [username...]

Credentials are written to ``STAFF_CREDENTIALS_PATH`` (or a container-local
file by default) so callers can copy them to a root-only host path.
"""

import os
import secrets
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.admin import hash_password
from app.db.session import SessionLocal
from app.models import Staff, Store


def setup_staff(db: Session, usernames: list[str]) -> list[tuple[str, str]]:
    stores = list(db.scalars(select(Store).order_by(Store.id)))
    if len(stores) != 1:
        raise RuntimeError("初始化员工要求数据库中恰好存在一个唯一门店")

    credentials: list[tuple[str, str]] = []
    for username in usernames:
        if db.scalar(select(Staff).where(Staff.username == username)) is not None:
            continue
        password = secrets.token_urlsafe(8)
        db.add(Staff(
            username=username,
            password_hash=hash_password(password),
            name=username,
            role="manager",
            status="active",
            store_id=stores[0].id,
        ))
        credentials.append((username, password))
    db.commit()
    return credentials


def write_credentials(credentials_path: Path, credentials: list[tuple[str, str]]) -> None:
    descriptor = os.open(credentials_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    if hasattr(os, "fchmod"):
        os.fchmod(descriptor, 0o600)
    else:
        os.chmod(credentials_path, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as credential_file:
        for username, password in credentials:
            credential_file.write(f"username: {username}\npassword: {password}\n")


def main(args: list[str]) -> None:
    usernames = [username.strip() for username in args if username.strip()]
    if not usernames:
        raise SystemExit("用法: setup_staff.py <username> [username...]")

    with SessionLocal() as db:
        credentials = setup_staff(db, usernames)
    credentials_path = Path(os.environ.get("STAFF_CREDENTIALS_PATH", "/tmp/staff-credentials.txt"))
    write_credentials(credentials_path, credentials)
    print(f"STAFF_SETUP_DONE created={len(credentials)}")


if __name__ == "__main__":
    main(sys.argv[1:])
