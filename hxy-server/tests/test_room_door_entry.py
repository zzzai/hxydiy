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

def test_whole_room_door_shares_one_cart_and_honors_disabled_qr(daily):
    client, factory, ids, headers = daily
    with factory.begin() as db:
        store = db.get(Store, ids["store"])
        store.status = "open"
        room = Room(store_id=store.id, code="shared-room", name="杜若", customer_label="杜若",
                    room_type="room", is_service_position=True, is_space_container=False, capacity=2)
        db.add(room)
        db.flush()
        qr = ServicePositionQr(public_id=str(uuid4()), store_id=store.id, room_id=room.id, source="room_qr", status="active")
        _ensure_position_short_code_hash(qr)
        db.add(qr)
        db.flush()
        qr_id, room_id = qr.id, room.id
    sheet = "/api/v1/admin/service-positions/door-print-sheet"
    item, = [v for v in client.get(sheet, headers=headers["manager"]).json()["items"] if v["code"] == "shared-room"]
    assert item["name"] == "杜若" and item["shared_room"]
    token, = parse_qs(urlsplit(item["url"]).query)["door"]
    door_path = "/api/v1/room-doors/" + token
    response = client.get(door_path)
    assert response.headers["cache-control"] == "no-store"
    door = response.json()
    assert door["room_name"] == "杜若" and door["beds"] == []
    redirect = client.get(door["order_url"], follow_redirects=False)
    assert redirect.status_code == 307
    query = parse_qs(urlsplit(redirect.headers["location"]).query)
    request = {"store_id": ids["store"], "position_code": "shared-room", "source": "room_qr", "entry_token": query["qr"][0]}
    first = client.post("/api/v1/entry-sessions", json=request)
    client.cookies.clear()
    second = client.post("/api/v1/entry-sessions", json=request)
    assert first.status_code == second.status_code == 200
    a, b = first.json(), second.json()
    assert a["position"]["id"] == b["position"]["id"] == room_id
    assert a["position"]["customer_label"] == "杜若"
    assert a["session"]["id"] == b["session"]["id"] and a["occupancy"]["id"] == b["occupancy"]["id"]
    assert a["collaboration_mode"] == b["collaboration_mode"] == "shared_draft"
    assert a["collaboration_token"] != b["collaboration_token"]
    with factory.begin() as db:
        db.get(ServicePositionQr, qr_id).status = "disabled"
    assert client.get(door_path).json()["order_url"] is None
    assert [v["url"] for v in client.get(sheet, headers=headers["manager"]).json()["items"] if v["code"] == "shared-room"] == [None]
