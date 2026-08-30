"""Initialize the standalone DIY menu database without demo customers or orders."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PageContent, Room, Store
from app.seed import seed
from scripts.sync_final_menu import sync_final_menu


ROOM_SPECS = [
    ("sofa-01", "1号沙发", "sofa", "1号沙发", True, 0.08, 0.14, 0.22, 0.14),
    ("sofa-02", "2号沙发", "sofa", "2号沙发", True, 0.08, 0.34, 0.22, 0.14),
    ("sofa-03", "3号沙发", "sofa", "3号沙发", True, 0.08, 0.54, 0.22, 0.14),
    ("sofa-04", "4号沙发", "sofa", "4号沙发", True, 0.08, 0.74, 0.22, 0.14),
    ("sofa-05", "5号沙发", "sofa", "5号沙发", True, 0.70, 0.14, 0.22, 0.14),
    ("sofa-06", "6号沙发", "sofa", "6号沙发", True, 0.70, 0.34, 0.22, 0.14),
    ("sofa-07", "7号沙发", "sofa", "7号沙发", True, 0.70, 0.54, 0.22, 0.14),
    ("sofa-08", "8号沙发", "sofa", "8号沙发", True, 0.70, 0.74, 0.22, 0.14),
]

SPACE_SPECS = [
    ("room-01", "1号房间", "massage"),
    ("room-02", "2号房间", "massage"),
    ("room-03", "3号房间", "massage"),
    ("room-04", "4号房间", "massage"),
    ("room-05", "5号房间", "spa"),
    ("room-06", "6号房间", "spa"),
    ("room-07", "7号房间", "spa"),
]

BED_SPECS = [
    ("bed-01a", "1号房间 A 床", "room-01", 0.33, 0.11, 0.10, 0.14),
    ("bed-01b", "1号房间 B 床", "room-01", 0.45, 0.11, 0.10, 0.14),
    ("bed-02a", "2号房间 A 床", "room-02", 0.57, 0.11, 0.10, 0.14),
    ("bed-02b", "2号房间 B 床", "room-02", 0.33, 0.40, 0.10, 0.14),
    ("bed-03a", "3号房间 A 床", "room-03", 0.45, 0.40, 0.10, 0.14),
    ("bed-04a", "4号房间 A 床", "room-04", 0.57, 0.40, 0.10, 0.14),
    ("bed-05a", "5号房间 A 床", "room-05", 0.33, 0.69, 0.10, 0.14),
    ("bed-06a", "6号房间 A 床", "room-06", 0.45, 0.69, 0.10, 0.14),
    ("bed-07a", "7号房间 A 床", "room-07", 0.57, 0.69, 0.10, 0.14),
]


def bootstrap_diy_store(db: Session) -> None:
    if db.scalar(select(Store).limit(1)) is None:
        seed(db)
    store = db.scalar(select(Store).limit(1))
    if store is None:
        raise RuntimeError("DIY 门店初始化失败")

    # 已存在的门店也要同步确认后的菜单；价格只追加新版本，不删除历史。
    sync_final_menu(db, store.id, apply=True)

    for order, (code, name, room_type, label, selectable, x, y, width, height) in enumerate(ROOM_SPECS, 1):
        room = db.scalar(select(Room).where(Room.code == code))
        if room is None:
            room = Room(store_id=store.id, code=code, name=name)
            db.add(room)
        room.store_id = store.id
        room.name = name
        room.room_type = room_type
        room.room_group = "sofa"
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
        room.parent_room_id = None
        room.is_space_container = False
        room.is_service_position = True

    containers: dict[str, Room] = {}
    for offset, (code, name, group) in enumerate(SPACE_SPECS, len(ROOM_SPECS) + 1):
        room = db.scalar(select(Room).where(Room.code == code))
        if room is None:
            room = Room(store_id=store.id, code=code, name=name)
            db.add(room)
        room.store_id = store.id
        room.name = name
        room.room_type = "room"
        room.room_group = group
        room.floor = "1F"
        room.capacity = 2 if code in {"room-01", "room-02"} else 1
        room.status = "available"
        room.customer_label = ""
        room.customer_selectable = False
        room.operational_status = "active"
        room.sort_order = offset
        room.parent_room_id = None
        room.is_space_container = True
        room.is_service_position = False
        containers[code] = room
    db.flush()

    for offset, (code, name, parent_code, x, y, width, height) in enumerate(BED_SPECS, len(ROOM_SPECS) + len(SPACE_SPECS) + 1):
        bed = db.scalar(select(Room).where(Room.code == code))
        if bed is None:
            bed = Room(store_id=store.id, code=code, name=name)
            db.add(bed)
        parent = containers[parent_code]
        bed.store_id = store.id
        bed.name = name
        bed.room_type = "bed"
        bed.room_group = parent.room_group
        bed.floor = parent.floor
        bed.capacity = 1
        bed.status = "available"
        bed.customer_label = name
        bed.customer_selectable = False
        bed.operational_status = "active"
        bed.sort_order = offset
        bed.map_x = x
        bed.map_y = y
        bed.map_width = width
        bed.map_height = height
        bed.parent_room_id = parent.id
        bed.is_space_container = False
        bed.is_service_position = True

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
