"""Initialize the standalone DIY menu database without demo customers or orders."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PageContent, Room, Store
from app.seed import seed


ROOM_SPECS = [
    ("sofa-01", "1号沙发", "sofa", "1号沙发", True, 0.08, 0.14, 0.22, 0.14),
    ("sofa-02", "2号沙发", "sofa", "2号沙发", True, 0.08, 0.34, 0.22, 0.14),
    ("sofa-03", "3号沙发", "sofa", "3号沙发", True, 0.08, 0.54, 0.22, 0.14),
    ("sofa-04", "4号沙发", "sofa", "4号沙发", True, 0.08, 0.74, 0.22, 0.14),
    ("sofa-05", "5号沙发", "sofa", "5号沙发", True, 0.70, 0.14, 0.22, 0.14),
    ("sofa-06", "6号沙发", "sofa", "6号沙发", True, 0.70, 0.34, 0.22, 0.14),
    ("sofa-07", "7号沙发", "sofa", "7号沙发", True, 0.70, 0.54, 0.22, 0.14),
    ("sofa-08", "8号沙发", "sofa", "8号沙发", True, 0.70, 0.74, 0.22, 0.14),
    ("room-01", "1号房间", "room", "当前房间", False, 0.38, 0.22, 0.24, 0.22),
    ("room-02", "2号房间", "room", "当前房间", False, 0.38, 0.56, 0.24, 0.22),
]


def bootstrap_diy_store(db: Session) -> None:
    if db.scalar(select(Store).limit(1)) is None:
        seed(db)
    store = db.scalar(select(Store).limit(1))
    if store is None:
        raise RuntimeError("DIY 门店初始化失败")

    for order, (code, name, room_type, label, selectable, x, y, width, height) in enumerate(ROOM_SPECS, 1):
        room = db.scalar(select(Room).where(Room.code == code))
        if room is None:
            room = Room(store_id=store.id, code=code, name=name)
            db.add(room)
        room.store_id = store.id
        room.name = name
        room.room_type = room_type
        room.room_group = room_type
        room.floor = "1F"
        room.capacity = 1
        room.status = "available"
        room.customer_label = label
        room.customer_selectable = selectable
        room.operational_status = "active"
        room.map_x = x
        room.map_y = y
        room.map_width = width
        room.map_height = height
        room.sort_order = order

    content = db.scalar(select(PageContent).where(PageContent.store_id == store.id, PageContent.page_key == "diy-home"))
    if content is None:
        db.add(PageContent(
            store_id=store.id,
            page_key="diy-home",
            title="到店选项目",
            subtitle="按需要，自由搭配",
            tea_options=[
                {"name": "老姜茶", "note": "辛香温润"},
                {"name": "陈皮茶", "note": "清香顺口"},
                {"name": "玫瑰茶", "note": "柔和花香"},
            ],
            published=False,
        ))
    db.commit()


if __name__ == "__main__":
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        bootstrap_diy_store(session)
    print("DIY_STORE_READY")
