# -*- coding: utf-8 -*-
"""初始化管理员账号：密码随机生成，凭据写入容器 /tmp（宿主 docker cp 取回）。
用法: docker exec -e PYTHONPATH=/app hxy-api python /tmp/setup_admin.py
"""
import hashlib
import os
import secrets

from app.db.session import SessionLocal
from app.models import Staff

pwd = secrets.token_urlsafe(12)
salt = os.urandom(16).hex()
digest = hashlib.pbkdf2_hmac("sha256", pwd.encode(), salt.encode(), 120_000).hex()
stored = f"{salt}${digest}"

db = SessionLocal()
staff = db.query(Staff).filter(Staff.username == "admin").first()
if staff:
    staff.password_hash = stored
else:
    db.add(Staff(username="admin", password_hash=stored, name="店长",
                 role="admin", status="active"))
db.commit()
db.close()

with open("/tmp/admin-credentials.txt", "w") as f:
    f.write(f"username: admin\npassword: {pwd}\n")
print("ADMIN_SETUP_DONE")
