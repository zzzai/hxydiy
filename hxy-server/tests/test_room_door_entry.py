from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from app.api.occupancies import _ensure_position_short_code_hash
from app.models import AuditLog, PositionOccupancy, Room, SelectionSession, ServicePositionQr, Store
from test_manager_daily import daily


def test_door_sheet_and_scoped_bed_selection(daily):
    client, factory, ids, headers = daily
    with factory.begin() as db:
        store = db.get(Store, ids["store"])
        store.status = "open"
        other = Store(store_code="door-other", name="Other store", address="Synthetic")
        db.add(other)
        db.flush()
        def room(code, kind, store_id=store.id, parent=None, live=True):
            item = Room(store_id=store_id, parent_room_id=parent, code=code, name=code, room_type=kind,
                        is_space_container=kind == "room", is_service_position=kind != "room")
            db.add(item)
            db.flush()
            if kind != "room":
                qr = ServicePositionQr(public_id=str(uuid4()), room_id=item.id, store_id=store_id,
                                       status="active" if live else "disabled")
                _ensure_position_short_code_hash(qr)
                db.add(qr)
                db.flush()
            return item
        room("sofa-1", "sofa")
        single = room("single", "room")
        multi = room("multiple", "room")
        room("bed-single", "bed", parent=single.id)
        a = room("bed-a", "bed", parent=multi.id)
        room("bed-b", "bed", parent=multi.id)
        room("bed-c", "bed", parent=multi.id, live=False)
        room("another-store", "sofa", store_id=other.id)
        room("wrong-store-child", "bed", store_id=other.id, parent=multi.id)
        other_door = room("other-room", "room", store_id=other.id)
        a_id, multi_id, other_id = a.id, multi.id, other_door.id
    endpoint = "/api/v1/admin/service-positions/door-print-sheet"
    assert client.get(endpoint).status_code == 401
    result = client.get(endpoint, headers=headers["manager"])
    assert result.status_code == 200, result.text
    sheet = {item["code"]: item["url"] for item in result.json()["items"]}
    assert set(sheet) == {"single", "multiple", "sofa-1"} and len(set(sheet.values())) == 3
    assert urlsplit(sheet["sofa-1"]).path.startswith("/api/v1/q/")
    def code(key):
        return parse_qs(urlsplit(sheet[key]).query)["door"][0]
    def public(token):
        return client.get("/api/v1/room-doors/" + token)
    assert len(public(code("single")).json()["beds"]) == 1
    assert public(code("single")).json()["beds"][0]["url"].startswith("/api/v1/q/")
    multiple = public(code("multiple"))
    assert multiple.headers["cache-control"] == "no-store"
    beds = multiple.json()["beds"]
    assert [b["name"] for b in beds] == ["bed-a", "bed-b", "bed-c"]
    assert beds[0]["url"] != beds[1]["url"] and beds[2]["url"] is None
    parts = code("multiple").split(".")
    assert public(f"{parts[0]}.{other_id}.{parts[2]}").status_code == 404
    assert public(code("multiple") + "xx").status_code == 404
    with factory.begin() as db:
        assert db.query(PositionOccupancy).count() == db.query(SelectionSession).count() == db.query(AuditLog).count() == 0
        db.get(Room, a_id).operational_status = "inactive"
    assert public(code("multiple")).json()["beds"][0]["url"] is None
    with factory.begin() as db:
        db.get(Room, multi_id).operational_status = "inactive"
    assert public(code("multiple")).status_code == 404
