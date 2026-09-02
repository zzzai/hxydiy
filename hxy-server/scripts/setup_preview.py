"""Create deterministic local data for browser acceptance testing.

Run with a dedicated SQLite URL, for example:
DATABASE_URL=sqlite:///../.workbuddy/tmp/hxy_preview.db python scripts/setup_preview.py
"""

from datetime import datetime
import os
from pathlib import Path
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.api.admin import hash_password
from app.core.config import settings
from app.db.session import Base, SessionLocal, engine
from app.models import (
    AutomationRule,
    CustomerSegment,
    CustomerTag,
    CustomerTagRelation,
    EventLog,
    Order,
    Project,
    Room,
    RoomAssignment,
    Staff,
    Store,
    Technician,
    User,
)
from scripts.bootstrap_diy_store import bootstrap_diy_store


def setup_preview() -> None:
    if settings.environment == "production" or not settings.database_url.startswith("sqlite"):
        raise RuntimeError("预览数据只能写入非生产 SQLite 数据库")

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        bootstrap_diy_store(db)
        store = db.scalar(select(Store).limit(1))
        if store is None:
            raise RuntimeError("门店种子数据初始化失败")
        store.status = "open"

        staff = db.scalar(select(Staff).where(Staff.username == "admin"))
        if staff is None:
            staff = Staff(username="admin", name="预览管理员", role="admin")
            db.add(staff)
        preview_password = os.getenv("HXY_PREVIEW_ADMIN_PASSWORD") or secrets.token_urlsafe(12)
        staff.password_hash = hash_password(preview_password)
        staff.store_id = store.id
        staff.status = "active"

        tech_specs = [
            ("tech-01", "王师傅", "高级", "available", 0.35),
            ("tech-02", "李师傅", "中级", "busy", 0.30),
            ("tech-03", "陈师傅", "高级", "available", 0.35),
        ]
        techs = []
        for order, (code, name, level, status, rate) in enumerate(tech_specs, 1):
            tech = db.scalar(select(Technician).where(Technician.code == code))
            if tech is None:
                tech = Technician(store_id=store.id, code=code, name=name)
                db.add(tech)
            tech.level = level
            tech.gender = "女" if code == "tech-02" else "男"
            tech.status = status
            tech.default_commission_rate = rate
            tech.sort_order = order
            techs.append(tech)

        db.flush()
        projects = list(db.scalars(select(Project)).all())
        assignment_room = db.scalar(select(Room).where(Room.code == "sofa-02"))
        if not db.scalar(select(RoomAssignment).limit(1)) and projects and assignment_room:
            db.add(RoomAssignment(
                room_id=assignment_room.id,
                technician_id=techs[0].id,
                project_ids=[p.id for p in projects[:3]],
            ))

        users = []
        for idx, (name, member, balance) in enumerate([
            ("林女士", True, 50000),
            ("周先生", False, 0),
            ("陈阿姨", True, 12800),
            ("小满", False, 0),
        ], 1):
            user = db.scalar(select(User).where(User.openid == f"preview-user-{idx}"))
            if user is None:
                user = User(openid=f"preview-user-{idx}")
                db.add(user)
            user.nickname = name
            user.phone = f"1380000{idx:04d}"
            user.is_member = member
            user.member_type = "stored" if member else None
            user.balance_cents = balance
            users.append(user)

        tag_specs = [("高频顾客", "#1677ff"), ("草本沐足", "#1f8f75"), ("需回访", "#d46b08")]
        tags = []
        for name, color in tag_specs:
            tag = db.scalar(select(CustomerTag).where(CustomerTag.name == name))
            if tag is None:
                tag = CustomerTag(name=name, color=color)
                db.add(tag)
            tags.append(tag)
        db.flush()
        if not db.scalar(select(CustomerTagRelation).limit(1)):
            db.add_all([
                CustomerTagRelation(user_id=users[0].id, tag_id=tags[0].id),
                CustomerTagRelation(user_id=users[0].id, tag_id=tags[1].id),
                CustomerTagRelation(user_id=users[2].id, tag_id=tags[2].id),
            ])

        if not db.scalar(select(CustomerSegment).limit(1)):
            db.add(CustomerSegment(
                name="活跃会员",
                description="已开通会员且近期有到店记录",
                conditions={"is_member": True},
                user_count=2,
            ))
        if not db.scalar(select(AutomationRule).limit(1)):
            db.add(AutomationRule(
                name="服务完成后关怀",
                description="服务完成后进入回访队列",
                trigger_event="order_completed",
                actions=[{"type": "add_tag", "tag_id": tags[2].id}],
                cooldown_days=7,
            ))

        today = datetime.now().date().isoformat()
        order_specs = [
            ("PREVIEW-PAID", users[0], "paid", "paid", "14:00", 8900),
            ("PREVIEW-SERVICE", users[1], "in_service", "paid", "15:00", 9900),
            ("PREVIEW-CHECKOUT", users[2], "pending_checkout", "paid", "16:00", 13900),
            ("PREVIEW-COMPLETED", users[3], "completed", "paid", "11:00", 2990),
        ]
        for order_no, user, status, pay_status, booking_time, amount in order_specs:
            order = db.scalar(select(Order).where(Order.order_no == order_no))
            if order is None:
                order = Order(
                    order_no=order_no,
                    order_type="service",
                    user_id=user.id,
                    store_id=store.id,
                )
                db.add(order)
            order.items = [{"name": "闲享轻养沐足", "quantity": 1}]
            order.booking_date = today
            order.booking_time = booking_time
            order.total_amount_cents = amount
            order.pay_amount_cents = amount
            order.status = status
            order.pay_status = pay_status

        if not db.scalar(select(EventLog).limit(1)):
            db.add_all([
                EventLog(user_id=users[0].id, event="page_view", page="home"),
                EventLog(user_id=users[1].id, event="page_view", page="projects"),
                EventLog(user_id=users[0].id, event="click_project", page="projects"),
            ])
        db.commit()

    print(f"PREVIEW_READY username=admin password={preview_password}")


if __name__ == "__main__":
    setup_preview()
