from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import Order, Staff, Store, User
from app.models.operations import Technician
from app.models.service import ServiceOrder, Visit


class TestTechnicianServiceScope:
    def setup_method(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        with self.SessionLocal() as db:
            own_store = Store(store_code="tech-scope-own", name="本店", address="本店地址")
            other_store = Store(store_code="tech-scope-other", name="他店", address="他店地址")
            db.add_all([own_store, other_store])
            db.flush()
            technician = Technician(
                store_id=own_store.id,
                code="TECH-SCOPE",
                name="本店技师",
                status="available",
            )
            own_user = User(
                openid="tech-scope-own-user",
                nickname="本店顾客",
                phone="13800138000",
                is_member=True,
            )
            other_user = User(
                openid="tech-scope-other-user",
                nickname="他店顾客",
                phone="13900139000",
                is_member=True,
            )
            db.add_all([technician, own_user, other_user])
            db.flush()
            staff = Staff(
                username="tech-scope-staff",
                password_hash=hash_password("tech-pass"),
                name="本店技师",
                role="technician",
                status="active",
                store_id=own_store.id,
                technician_id=technician.id,
            )
            db.add(staff)
            db.flush()

            own_active = self._add_service_order(
                db, own_store.id, own_user.id, "SCOPE-OWN-ACTIVE", "in_service", 12800
            )
            own_unassigned = self._add_service_order(
                db, own_store.id, own_user.id, "SCOPE-OWN-UNASSIGNED", "draft", 9900
            )
            own_history = self._add_service_order(
                db, own_store.id, own_user.id, "SCOPE-OWN-HISTORY", "completed", 18800
            )
            self._add_service_order(
                db, other_store.id, other_user.id, "SCOPE-OTHER-ACTIVE", "in_service", 26800
            )
            db.commit()
            self.staff_id = staff.id
            self.active_id = own_active.id
            self.unassigned_id = own_unassigned.id
            self.history_id = own_history.id

        app.dependency_overrides[get_db] = self._override_get_db
        self.client = TestClient(app)
        self.headers = {
            "Authorization": f"Bearer {create_staff_token(self.staff_id, 'technician')}"
        }

    @staticmethod
    def _add_service_order(db, store_id, user_id, order_no, status, amount):
        order = Order(
            order_no=order_no,
            order_type="service",
            user_id=user_id,
            store_id=store_id,
            items=[{"name": "足浴", "price_cents": amount}],
            total_amount_cents=amount,
            pay_amount_cents=amount,
            status="in_service" if status != "completed" else "completed",
            pay_status="paid",
        )
        db.add(order)
        db.flush()
        visit = Visit(store_id=store_id, order_id=order.id, user_id=user_id, status=status)
        db.add(visit)
        db.flush()
        service_order = ServiceOrder(
            store_id=store_id,
            order_id=order.id,
            visit_id=visit.id,
            status=status,
            items=[{"name": "足浴", "price_cents": amount}],
            total_amount_cents=amount,
        )
        db.add(service_order)
        db.flush()
        return service_order

    def _override_get_db(self):
        with self.SessionLocal() as db:
            yield db

    def teardown_method(self):
        app.dependency_overrides.clear()
        self.client.close()
        self.engine.dispose()

    def test_default_list_is_all_in_progress_orders_in_authenticated_store_and_redacted(self):
        response = self.client.get("/api/v1/admin/v2/service-orders", headers=self.headers)

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["total"] == 2
        assert {item["id"] for item in payload["items"]} == {
            self.active_id,
            self.unassigned_id,
        }
        for item in payload["items"]:
            assert item["customer"]["phone_masked"] == "138****8000"
            assert "phone" not in item["customer"]
            assert "is_member" not in item["customer"]
            assert "member_type" not in item["customer"]
            assert "total_amount_cents" not in item
            assert all("price_cents" not in service for service in item["items"])
            assert "profile" not in item
            assert "profile_records" not in item

    def test_history_filter_is_store_scoped_and_paginated(self):
        response = self.client.get(
            "/api/v1/admin/v2/service-orders",
            headers=self.headers,
            params={"status": "history", "page": 1, "page_size": 1},
        )

        assert response.status_code == 200, response.text
        assert response.json()["total"] == 1
        assert [item["id"] for item in response.json()["items"]] == [self.history_id]

    def test_technician_cannot_run_service_order_operations(self):
        legacy_price_board = self.client.get(
            "/api/v1/operations/live-board",
            headers=self.headers,
        )
        ready = self.client.post(
            f"/api/v1/operations/service-orders/{self.active_id}/ready",
            headers=self.headers,
            json={"idempotency_key": "tech-scope-ready"},
        )
        settle = self.client.post(
            f"/api/v1/operations/service-orders/{self.active_id}/settle",
            headers=self.headers,
            json={
                "idempotency_key": "tech-scope-settle",
                "payment_method": "cash",
                "received_amount_cents": 12800,
                "payment_reference": "",
            },
        )

        assert legacy_price_board.status_code == 403, legacy_price_board.text
        assert ready.status_code == 403, ready.text
        assert settle.status_code == 403, settle.text
