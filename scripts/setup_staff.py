# -*- coding: utf-8 -*-
"""批量创建员工账号（staff 角色，随机密码输出到 stdout）。
用法: docker exec -e PYTHONPATH=/app hxy-api python /tmp/setup_staff.py <username> [username...]
宿主捕获: docker exec ... > /tmp/staff-creds.txt && cat /tmp/staff-creds.txt
"""
import hashlib
import os
import secrets
import sys

from app.db.session import SessionLocal
from app.models import Staff


def make_hash(pwd: str) -> str:
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", pwd.encode(), salt.encode(), 120_000).hex()
    return f"{salt}${digest}"


usernames = [u.strip() for u in sys.argv[1:] if u.strip()]
if not usernames:
    print("用法: setup_staff.py <username> [username...]")
    sys.exit(1)

db = SessionLocal()
out_lines = []
for uname in usernames:
    if db.query(Staff).filter(Staff.username == uname).first():
        print(f"SKIP {uname} 已存在", file=sys.stderr)
        continue
    pwd = secrets.token_urlsafe(8)
    db.add(Staff(username=uname, password_hash=make_hash(pwd),
                 name=uname, role="staff", status="active"))
    out_lines.append(f"username: {uname}\npassword: {pwd}\n")
db.commit()
db.close()

for chunk in out_lines:
    print(chunk, end="")
print(f"CREATED {len(out_lines)}", file=sys.stderr)
