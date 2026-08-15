import hashlib
import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import AuditLog, Order, PositionOccupancy, Project, SelectionRevision, SelectionSession, ServiceFeedback, ServiceLine, Staff, Store, User
import app.models as models
from app.models.operations import Room
from app.models.operations import Technician
from app.models.service import ServiceOrder, Visit


class DiyCounterCheckoutApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        with self.SessionLocal() as db:
            store = Store(store_code="diy-counter-store", name="DIY 收款测试门店", address="测试地址")
            db.add(store)
            db.flush()
            staff = Staff(
                username="diy-counter-admin", name="前台", role="admin", status="active",
                password_hash=hash_password("pass"), store_id=store.id,
            )
            customer = User(openid="diy-counter-customer", phone="13800138000", is_member=True)
            project = Project(
                store_id=store.id, code="DIY-COUNTER-PROJECT", category="bath",
                name="草本泡脚", publication_status="published",
            )
            room = Room(
                store_id=store.id, code="DIY-COUNTER-SOFA", name="测试沙发",
                room_type="sofa", customer_label="3 号沙发", status="available",
            )
            alternate_room = Room(
                store_id=store.id, code="DIY-COUNTER-ALT-SOFA", name="备用测试沙发",
                room_type="sofa", customer_label="4 号沙发", status="available",
            )
            technician = Technician(
                store_id=store.id, code="DIY-COUNTER-TECH", name="测试技师", status="available",
            )
            db.add_all([staff, customer, project, room, alternate_room, technician])
            db.flush()
            session = SelectionSession(
                id="diy-counter-selection", access_token_hash=hashlib.sha256(b"diy-counter-token").hexdigest(), store_id=store.id,
                customer_id=customer.id, source="personal_qr", device_label="顾客手机",
                status="submitted", items=[{
                    "project_id": project.id, "name": project.name, "code": project.code,
                    "quantity": 1, "item_type": "service", "chargeable": True,
                    "diy_preferences": ["暖泡舒缓"],
                }],
                pricing_snapshot={
                    "applied_price_type": "member", "store_subtotal_cents": 3990,
                    "store_total_cents": 3990, "member_total_cents": 2990,
                    "payable_total_cents": 2990,
                    "lines": [{
                        "line_index": 0, "project_id": project.id, "name": project.name,
                        "quantity": 1, "unit_payable_price_cents": 2990,
                        "payable_line_total_cents": 2990,
                    }],
                },
                store_total_cents=3990,
                member_total_cents=2990,
            )
            db.add(session)
            db.flush()
            db.add(PositionOccupancy(
                store_id=store.id, room_id=room.id, active_room_id=room.id,
                selection_session_id=session.id, active_session_id=session.id,
                status="waiting_service", source="personal_qr",
            ))
            db.commit()
            self.store_id = store.id
            self.staff_id = staff.id
            self.customer_id = customer.id
            self.session_id = session.id
            self.project_id = project.id
            self.room_id = room.id
            self.alternate_room_id = alternate_room.id
            self.technician_id = technician.id

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        self.headers = {"Authorization": f"Bearer {create_staff_token(self.staff_id, 'admin')}"}

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_counter_checkout_confirms_service_flow_without_collecting_payment(self):
        payload = {
            "idempotency_key": "diy-counter-checkout-1",
            "payment_method": "wechat_scan",
            "received_amount_cents": 2990,
            "payment_reference": "COUNTER-REF-1",
        }

        response = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/counter-checkout",
            headers=self.headers,
            json=payload,
        )

        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["selection_status"], "confirmed")
        self.assertEqual(result["order_status"], "checked_in")
        self.assertEqual(result["visit_status"], "waiting_assignment")
        self.assertEqual(result["service_order_status"], "draft")
        self.assertEqual(result["payable_total_cents"], 2990)

        replay = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/counter-checkout",
            headers=self.headers,
            json=payload,
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), result)

        with self.SessionLocal() as db:
            order = db.get(Order, result["order_id"])
            visit = db.get(Visit, result["visit_id"])
            service_order = db.get(ServiceOrder, result["service_order_id"])
            session = db.get(SelectionSession, self.session_id)
            occupancy = db.query(PositionOccupancy).filter(
                PositionOccupancy.selection_session_id == self.session_id,
            ).one()

            self.assertEqual(order.pay_status, "unpaid")
            self.assertEqual(order.pay_amount_cents, 2990)
            self.assertEqual(order.pay_transaction_id, "")
            self.assertEqual(order.items[0]["unit_payable_price_cents"], 2990)
            self.assertEqual(visit.order_id, order.id)
            self.assertEqual(service_order.order_id, order.id)
            self.assertEqual(service_order.total_amount_cents, 2990)
            self.assertEqual(session.fulfillment_order_id, order.id)
            self.assertEqual(occupancy.status, "waiting_service")

    def test_completed_diy_service_can_settle_without_technician_assignment(self):
        with self.SessionLocal() as db:
            session = db.get(SelectionSession, self.session_id)
            session.status = "confirmed"
            revision = SelectionRevision(
                id="direct-settlement-revision",
                selection_session_id=self.session_id,
                revision_no=1,
                state="confirmed",
                idempotency_key="direct-settlement-revision",
                snapshot={
                    "items": session.items,
                    "pricing": session.pricing_snapshot,
                },
            )
            db.add(revision)
            db.flush()
            db.add(ServiceLine(
                id="direct-settlement-line",
                selection_session_id=self.session_id,
                selection_revision_id=revision.id,
                snapshot=session.items[0],
                state="completed",
            ))
            occupancy = db.scalar(select(PositionOccupancy).where(
                PositionOccupancy.selection_session_id == self.session_id,
            ))
            occupancy.status = "post_service_present"
            occupancy.actual_service_end_at = datetime.now(timezone.utc)
            db.commit()

        response = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/settle",
            headers=self.headers,
            json={
                "idempotency_key": "direct-settlement",
                "payment_method": "wechat_scan",
                "received_amount_cents": 2990,
                "payment_reference": "DIRECT-SETTLEMENT-1",
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["order_status"], "completed")
        with self.SessionLocal() as db:
            order = db.get(Order, response.json()["order_id"])
            session = db.get(SelectionSession, self.session_id)
            self.assertEqual(order.pay_status, "paid")
            self.assertEqual(order.pay_transaction_id, "DIRECT-SETTLEMENT-1")
            self.assertEqual(session.fulfillment_order_id, order.id)
            self.assertIsNone(db.scalar(select(Visit).where(Visit.selection_session_id == self.session_id)))

    def test_diy_service_cannot_settle_before_service_completion(self):
        with self.SessionLocal() as db:
            session = db.get(SelectionSession, self.session_id)
            session.status = "confirmed"
            db.commit()

        response = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/settle",
            headers=self.headers,
            json={
                "idempotency_key": "early-direct-settlement",
                "payment_method": "cash",
                "received_amount_cents": 2990,
                "payment_reference": "",
            },
        )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "SERVICE_NOT_COMPLETED")

    def test_abnormal_service_requires_explicit_adjustment_before_settlement(self):
        with self.SessionLocal() as db:
            session = db.get(SelectionSession, self.session_id)
            session.status = "confirmed"
            revision = SelectionRevision(
                id="abnormal-settlement-revision",
                selection_session_id=self.session_id,
                revision_no=1,
                state="confirmed",
                idempotency_key="abnormal-settlement-revision",
                snapshot={"items": session.items, "pricing": session.pricing_snapshot},
            )
            db.add(revision)
            db.flush()
            db.add(ServiceLine(
                id="abnormal-settlement-line",
                selection_session_id=self.session_id,
                selection_revision_id=revision.id,
                snapshot=session.items[0],
                state="in_service",
                started_at=datetime.now(timezone.utc),
            ))
            occupancy = db.scalar(select(PositionOccupancy).where(
                PositionOccupancy.selection_session_id == self.session_id,
            ))
            occupancy.status = "cleaning"
            occupancy.actual_service_end_at = datetime.now(timezone.utc)
            occupancy.departed_at = datetime.now(timezone.utc)
            occupancy.release_reason = "顾客身体不适，服务提前结束"
            db.commit()

        response = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/settle",
            headers=self.headers,
            json={
                "idempotency_key": "abnormal-settlement-missing-adjustment",
                "payment_method": "cash",
                "received_amount_cents": 2990,
                "payment_reference": "",
            },
        )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "SERVICE_ADJUSTMENT_REQUIRED")

    def test_abnormal_service_adjustment_recalculates_payment_and_is_auditable(self):
        with self.SessionLocal() as db:
            session = db.get(SelectionSession, self.session_id)
            session.status = "confirmed"
            revision = SelectionRevision(
                id="abnormal-adjusted-revision",
                selection_session_id=self.session_id,
                revision_no=1,
                state="confirmed",
                idempotency_key="abnormal-adjusted-revision",
                snapshot={"items": session.items, "pricing": session.pricing_snapshot},
            )
            db.add(revision)
            db.flush()
            db.add(ServiceLine(
                id="abnormal-adjusted-line",
                selection_session_id=self.session_id,
                selection_revision_id=revision.id,
                snapshot=session.items[0],
                state="in_service",
                started_at=datetime.now(timezone.utc),
            ))
            occupancy = db.scalar(select(PositionOccupancy).where(
                PositionOccupancy.selection_session_id == self.session_id,
            ))
            occupancy.status = "cleaning"
            occupancy.actual_service_end_at = datetime.now(timezone.utc)
            occupancy.departed_at = datetime.now(timezone.utc)
            occupancy.release_reason = "顾客身体不适，服务提前结束"
            db.commit()

        response = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/settle",
            headers=self.headers,
            json={
                "idempotency_key": "abnormal-adjusted-settlement",
                "payment_method": "cash",
                "received_amount_cents": 1990,
                "payment_reference": "ABNORMAL-CASH-1",
                "service_adjustment_cents": 1000,
                "adjustment_reason_code": "service_aborted",
                "responsibility": "store",
                "reason": "服务中止，减免部分项目费用",
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["original_payable_total_cents"], 2990)
        self.assertEqual(result["service_adjustment_cents"], 1000)
        self.assertEqual(result["payable_total_cents"], 1990)
        adjustment_model = getattr(models, "SettlementAdjustment", None)
        self.assertIsNotNone(adjustment_model)
        with self.SessionLocal() as db:
            order = db.get(Order, result["order_id"])
            line = db.get(ServiceLine, "abnormal-adjusted-line")
            adjustment = db.scalar(select(adjustment_model).where(
                adjustment_model.order_id == order.id,
                adjustment_model.adjustment_type == "service_waiver",
            ))
            self.assertEqual(order.pay_amount_cents, 1990)
            self.assertEqual(line.state, "cancelled")
            self.assertEqual(adjustment.amount_cents, 1000)
            self.assertEqual(adjustment.reason_code, "service_aborted")
            self.assertEqual(adjustment.responsibility, "store")
            self.assertEqual(adjustment.original_amount_cents, 2990)
            self.assertEqual(adjustment.final_amount_cents, 1990)
            order_id = order.id

        refund = self.client.post(
            f"/api/v1/operations/orders/{order_id}/refund-note",
            headers=self.headers,
            json={
                "idempotency_key": "abnormal-partial-refund",
                "amount_cents": 500,
                "reason_code": "customer_complaint",
                "responsibility": "store",
                "refund_reference": "OFFLINE-REFUND-1",
                "reason": "顾客投诉后线下退回",
            },
        )

        self.assertEqual(refund.status_code, 200, refund.text)
        self.assertEqual(refund.json()["refund_status"], "partially_refunded")
        self.assertEqual(refund.json()["refunded_amount_cents"], 500)
        orders = self.client.get("/api/v1/admin/orders", headers=self.headers)
        self.assertEqual(orders.status_code, 200, orders.text)
        order_summary = next(item for item in orders.json()["items"] if item["id"] == order_id)
        self.assertEqual(order_summary["pay_status"], "paid")
        self.assertEqual(order_summary["refund_status"], "partially_refunded")
        with self.SessionLocal() as db:
            order = db.get(Order, order_id)
            refund_adjustment = db.scalar(select(adjustment_model).where(
                adjustment_model.order_id == order_id,
                adjustment_model.adjustment_type == "refund_note",
            ))
            self.assertEqual(order.refund_status, "partially_refunded")
            self.assertEqual(order.pay_status, "paid")
            self.assertEqual(refund_adjustment.payment_allocation["refund_reference"], "OFFLINE-REFUND-1")

    def test_refund_notes_cannot_exceed_actual_paid_amount(self):
        with self.SessionLocal() as db:
            order = Order(
                order_no="REFUND-LIMIT-ORDER",
                order_type="service",
                user_id=self.customer_id,
                store_id=self.store_id,
                items=[],
                total_amount_cents=1000,
                pay_amount_cents=1000,
                status="completed",
                pay_status="paid",
            )
            db.add(order)
            db.commit()
            order_id = order.id

        response = self.client.post(
            f"/api/v1/operations/orders/{order_id}/refund-note",
            headers=self.headers,
            json={
                "idempotency_key": "refund-over-limit",
                "amount_cents": 1001,
                "reason_code": "other",
                "responsibility": "store",
                "reason": "超额退款测试",
            },
        )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "REFUND_AMOUNT_EXCEEDED")

    def test_counter_checkout_uses_confirmed_revision_member_price_snapshot(self):
        with self.SessionLocal() as db:
            revision = SelectionRevision(
                id="diy-counter-revision-member",
                selection_session_id=self.session_id,
                revision_no=1,
                state="confirmed",
                idempotency_key="diy-counter-member-price",
                snapshot={
                    "items": [{"project_id": self.project_id, "name": "草本泡脚", "quantity": 1}],
                    "pricing": {
                        "store_total_cents": 3990,
                        "member_total_cents": 2990,
                        "payable_total_cents": 2990,
                        "lines": [{
                            "project_id": self.project_id,
                            "name": "草本泡脚",
                            "quantity": 1,
                            "unit_payable_price_cents": 2990,
                            "payable_line_total_cents": 2990,
                        }],
                    },
                },
            )
            db.add(revision)
            db.add(ServiceLine(
                id="diy-counter-member-line",
                selection_session_id=self.session_id,
                selection_revision_id=revision.id,
                snapshot={"project_id": self.project_id, "name": "草本泡脚", "quantity": 1},
                state="pending",
            ))
            db.commit()

        response = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/counter-checkout",
            headers=self.headers,
            json={
                "idempotency_key": "diy-counter-member-checkout",
                "payment_method": "wechat_scan",
                "received_amount_cents": 2990,
                "payment_reference": "COUNTER-MEMBER-REF-1",
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["payable_total_cents"], 2990)
        with self.SessionLocal() as db:
            order = db.get(Order, response.json()["order_id"])
            self.assertEqual(order.total_amount_cents, 2990)
            self.assertEqual(order.discount_cents, 1000)
            self.assertEqual(order.items[0]["unit_payable_price_cents"], 2990)

    def test_service_actions_keep_linked_position_in_sync(self):
        with self.SessionLocal() as db:
            revision = SelectionRevision(
                id="diy-counter-service-line-revision",
                selection_session_id=self.session_id,
                revision_no=1,
                state="confirmed",
                idempotency_key="diy-counter-service-line-revision",
                snapshot={
                    "items": [{"project_id": self.project_id, "name": "草本泡脚", "quantity": 1}],
                    "pricing": {
                        "store_total_cents": 3990,
                        "member_total_cents": 2990,
                        "payable_total_cents": 2990,
                        "lines": [{"project_id": self.project_id, "name": "草本泡脚", "quantity": 1}],
                    },
                },
            )
            db.add(revision)
            db.add(ServiceLine(
                id="diy-counter-service-line",
                selection_session_id=self.session_id,
                selection_revision_id=revision.id,
                snapshot={"project_id": self.project_id, "name": "草本泡脚", "quantity": 1},
                state="pending",
            ))
            db.commit()
        checkout = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/counter-checkout",
            headers=self.headers,
            json={
                "idempotency_key": "diy-counter-sync-checkout", "payment_method": "cash",
                "received_amount_cents": 2990, "payment_reference": "",
            },
        ).json()
        assigned = self.client.post(
            f"/api/v1/operations/visits/{checkout['visit_id']}/assign",
            headers=self.headers,
            json={
                "idempotency_key": "diy-counter-sync-assign", "technician_id": self.technician_id,
                "room_id": self.room_id, "project_ids": [self.project_id],
            },
        )
        self.assertEqual(assigned.status_code, 200, assigned.text)
        self.client.post(
            f"/api/v1/operations/service-orders/{checkout['service_order_id']}/ready",
            headers=self.headers, json={"idempotency_key": "diy-counter-sync-ready"},
        )
        started = self.client.post(
            f"/api/v1/operations/service-orders/{checkout['service_order_id']}/start",
            headers=self.headers, json={"idempotency_key": "diy-counter-sync-start"},
        )
        self.assertEqual(started.status_code, 200, started.text)
        with self.SessionLocal() as db:
            occupancy = db.query(PositionOccupancy).filter_by(selection_session_id=self.session_id).one()
            line = db.get(ServiceLine, "diy-counter-service-line")
            self.assertEqual(occupancy.status, "in_service")
            self.assertIsNotNone(occupancy.actual_start_at)
            self.assertEqual(line.state, "in_service")
            self.assertIsNotNone(line.started_at)

        finished = self.client.post(
            f"/api/v1/operations/service-orders/{checkout['service_order_id']}/finish",
            headers=self.headers, json={"idempotency_key": "diy-counter-sync-finish"},
        )
        self.assertEqual(finished.status_code, 200, finished.text)
        with self.SessionLocal() as db:
            occupancy = db.query(PositionOccupancy).filter_by(selection_session_id=self.session_id).one()
            line = db.get(ServiceLine, "diy-counter-service-line")
            self.assertEqual(occupancy.status, "post_service_present")
            self.assertIsNotNone(occupancy.actual_service_end_at)
            self.assertEqual(line.state, "completed")
            self.assertIsNotNone(line.completed_at)

    def test_diy_counter_assignment_must_use_the_currently_occupied_service_position(self):
        checkout = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/counter-checkout",
            headers=self.headers,
            json={
                "idempotency_key": "diy-counter-position-checkout", "payment_method": "cash",
                "received_amount_cents": 2990, "payment_reference": "",
            },
        )
        self.assertEqual(checkout.status_code, 200, checkout.text)

        assigned = self.client.post(
            f"/api/v1/operations/visits/{checkout.json()['visit_id']}/assign",
            headers=self.headers,
            json={
                "idempotency_key": "diy-counter-position-assign", "technician_id": self.technician_id,
                "room_id": self.alternate_room_id, "project_ids": [self.project_id],
            },
        )

        self.assertEqual(assigned.status_code, 409, assigned.text)
        self.assertEqual(assigned.json()["detail"]["code"], "DIY_POSITION_MISMATCH")
        with self.SessionLocal() as db:
            room = db.get(Room, self.alternate_room_id)
            self.assertEqual(room.status, "available")

    def test_diy_counter_position_cannot_move_after_front_desk_checkout(self):
        checkout = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/counter-checkout",
            headers=self.headers,
            json={
                "idempotency_key": "diy-counter-move-checkout", "payment_method": "cash",
                "received_amount_cents": 2990, "payment_reference": "",
            },
        )
        self.assertEqual(checkout.status_code, 200, checkout.text)
        with self.SessionLocal() as db:
            occupancy = db.scalar(select(PositionOccupancy).where(
                PositionOccupancy.selection_session_id == self.session_id,
            ))

        moved = self.client.post(
            f"/api/v1/admin/occupancies/{occupancy.id}/move",
            headers=self.headers,
            json={
                "target_room_id": self.alternate_room_id,
                "version": occupancy.version,
                "reason": "测试绕过已派钟服务位",
            },
        )

        self.assertEqual(moved.status_code, 409, moved.text)
        self.assertEqual(moved.json()["detail"]["code"], "DIY_POSITION_LOCKED")

    def test_diy_counter_position_actions_require_the_service_order_flow(self):
        checkout = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/counter-checkout",
            headers=self.headers,
            json={
                "idempotency_key": "diy-counter-direct-action-checkout", "payment_method": "cash",
                "received_amount_cents": 2990, "payment_reference": "",
            },
        )
        self.assertEqual(checkout.status_code, 200, checkout.text)
        with self.SessionLocal() as db:
            occupancy = db.scalar(select(PositionOccupancy).where(
                PositionOccupancy.selection_session_id == self.session_id,
            ))

        for action in ("start-service", "confirm-departure"):
            with self.subTest(action=action):
                response = self.client.post(
                    f"/api/v1/admin/occupancies/{occupancy.id}/{action}",
                    headers=self.headers,
                    json={},
                )
                self.assertEqual(response.status_code, 409, response.text)
                self.assertEqual(response.json()["detail"]["code"], "DIY_FULFILLMENT_OPERATION_REQUIRED")

        with self.SessionLocal() as db:
            occupancy = db.get(PositionOccupancy, occupancy.id)
            service_order = db.get(ServiceOrder, checkout.json()["service_order_id"])
            self.assertEqual(occupancy.status, "waiting_service")
            self.assertEqual(service_order.status, "draft")

    def test_diy_counter_departure_requires_the_service_order_to_be_settled(self):
        checkout = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/counter-checkout",
            headers=self.headers,
            json={
                "idempotency_key": "diy-counter-departure-checkout", "payment_method": "cash",
                "received_amount_cents": 2990, "payment_reference": "",
            },
        ).json()
        with self.SessionLocal() as db:
            occupancy = db.scalar(select(PositionOccupancy).where(
                PositionOccupancy.selection_session_id == self.session_id,
            ))

        departed = self.client.post(
            f"/api/v1/admin/occupancies/{occupancy.id}/confirm-departure",
            headers=self.headers,
            json={"reason": "测试绕过结算离位"},
        )

        self.assertEqual(departed.status_code, 409, departed.text)
        self.assertEqual(departed.json()["detail"]["code"], "DIY_FULFILLMENT_OPERATION_REQUIRED")
        with self.SessionLocal() as db:
            service_order = db.get(ServiceOrder, checkout["service_order_id"])
            self.assertEqual(service_order.status, "draft")

    def test_diy_counter_position_cannot_use_legacy_cleaning_completion(self):
        checkout = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/counter-checkout",
            headers=self.headers,
            json={
                "idempotency_key": "diy-counter-legacy-clean-checkout", "payment_method": "cash",
                "received_amount_cents": 2990, "payment_reference": "",
            },
        ).json()
        assigned = self.client.post(
            f"/api/v1/operations/visits/{checkout['visit_id']}/assign",
            headers=self.headers,
            json={
                "idempotency_key": "diy-counter-legacy-clean-assign", "technician_id": self.technician_id,
                "room_id": self.room_id, "project_ids": [self.project_id],
            },
        )
        self.assertEqual(assigned.status_code, 200, assigned.text)
        for action in ("ready", "start", "finish"):
            response = self.client.post(
                f"/api/v1/operations/service-orders/{checkout['service_order_id']}/{action}",
                headers=self.headers,
                json={"idempotency_key": f"diy-counter-legacy-clean-{action}"},
            )
            self.assertEqual(response.status_code, 200, response.text)
        settled = self.client.post(
            f"/api/v1/operations/service-orders/{checkout['service_order_id']}/settle",
            headers=self.headers,
            json={
                "idempotency_key": "diy-counter-legacy-clean-settle", "payment_method": "cash",
                "received_amount_cents": 2990, "payment_reference": "",
            },
        )
        self.assertEqual(settled.status_code, 200, settled.text)

        cleaned = self.client.post(
            f"/api/v1/operations/rooms/{self.room_id}/finish-cleaning",
            headers=self.headers,
            json={"idempotency_key": "diy-counter-legacy-clean-room"},
        )

        self.assertEqual(cleaned.status_code, 409, cleaned.text)
        self.assertEqual(cleaned.json()["detail"]["code"], "DIY_POSITION_OCCUPIED")

    def test_live_position_map_keeps_active_diy_state_when_legacy_flow_reserves_its_room(self):
        checkout = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/counter-checkout",
            headers=self.headers,
            json={
                "idempotency_key": "diy-counter-map-checkout", "payment_method": "cash",
                "received_amount_cents": 2990, "payment_reference": "",
            },
        ).json()
        assigned = self.client.post(
            f"/api/v1/operations/visits/{checkout['visit_id']}/assign",
            headers=self.headers,
            json={
                "idempotency_key": "diy-counter-map-assign", "technician_id": self.technician_id,
                "room_id": self.room_id, "project_ids": [self.project_id],
            },
        )
        self.assertEqual(assigned.status_code, 200, assigned.text)

        response = self.client.get(
            "/api/v1/admin/live-service-position-map",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200, response.text)
        position = next(item for item in response.json()["positions"] if item["id"] == self.room_id)
        self.assertEqual(position["state"], "waiting_service")
        self.assertEqual(position["occupancy"]["status"], "waiting_service")
        self.assertEqual(position["selection"]["fulfillment_order_id"], checkout["order_id"])

    def test_diy_counter_service_settlement_departure_cleaning_and_feedback_close_together(self):
        with self.SessionLocal() as db:
            revision = SelectionRevision(
                id="diy-counter-closure-revision",
                selection_session_id=self.session_id,
                revision_no=1,
                state="confirmed",
                idempotency_key="diy-counter-closure-revision",
                snapshot={
                    "items": [{"project_id": self.project_id, "name": "草本泡脚", "quantity": 1}],
                    "pricing": {
                        "store_total_cents": 3990,
                        "member_total_cents": 2990,
                        "payable_total_cents": 2990,
                        "lines": [{"project_id": self.project_id, "name": "草本泡脚", "quantity": 1}],
                    },
                },
            )
            db.add(revision)
            db.add(ServiceLine(
                id="diy-counter-closure-line",
                selection_session_id=self.session_id,
                selection_revision_id=revision.id,
                snapshot={"project_id": self.project_id, "name": "草本泡脚", "quantity": 1},
                state="pending",
            ))
            db.commit()

        checkout = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/counter-checkout",
            headers=self.headers,
            json={
                "idempotency_key": "diy-counter-closure-checkout", "payment_method": "cash",
                "received_amount_cents": 2990, "payment_reference": "DIY-CLOSURE-REF-1",
            },
        )
        self.assertEqual(checkout.status_code, 200, checkout.text)
        service_order_id = checkout.json()["service_order_id"]
        visit_id = checkout.json()["visit_id"]

        assigned = self.client.post(
            f"/api/v1/operations/visits/{visit_id}/assign",
            headers=self.headers,
            json={
                "idempotency_key": "diy-counter-closure-assign", "technician_id": self.technician_id,
                "room_id": self.room_id, "project_ids": [self.project_id],
            },
        )
        self.assertEqual(assigned.status_code, 200, assigned.text)
        for action in ("ready", "start", "finish"):
            response = self.client.post(
                f"/api/v1/operations/service-orders/{service_order_id}/{action}",
                headers=self.headers,
                json={"idempotency_key": f"diy-counter-closure-{action}"},
            )
            self.assertEqual(response.status_code, 200, response.text)

        settled = self.client.post(
            f"/api/v1/operations/service-orders/{service_order_id}/settle",
            headers=self.headers,
            json={
                "idempotency_key": "diy-counter-closure-settle", "payment_method": "cash",
                "received_amount_cents": 2990, "payment_reference": "DIY-CLOSURE-REF-1",
            },
        )
        self.assertEqual(settled.status_code, 200, settled.text)

        with self.SessionLocal() as db:
            occupancy = db.scalar(select(PositionOccupancy).where(PositionOccupancy.selection_session_id == self.session_id))
            self.assertEqual(occupancy.status, "post_service_present")
            self.assertIsNotNone(occupancy.actual_service_end_at)
            occupancy_id = occupancy.id

        departed = self.client.post(
            f"/api/v1/admin/occupancies/{occupancy_id}/confirm-departure",
            headers=self.headers,
            json={"reason": "顾客已离位"},
        )
        self.assertEqual(departed.status_code, 200, departed.text)
        self.assertEqual(departed.json()["status"], "cleaning")

        cleaned = self.client.post(
            f"/api/v1/admin/occupancies/{occupancy_id}/finish-cleaning",
            headers=self.headers,
            json={"reason": "清洁完成"},
        )
        self.assertEqual(cleaned.status_code, 200, cleaned.text)
        self.assertEqual(cleaned.json()["status"], "released")
        self.assertIsNone(cleaned.json()["active_room_id"])

        feedback = self.client.post(
            f"/api/v1/selection-sessions/{self.session_id}/feedback",
            headers={"X-Selection-Token": "diy-counter-token"},
            json={"rating": 5, "tags": ["服务细致"], "note": "很好"},
        )
        self.assertEqual(feedback.status_code, 200, feedback.text)

        with self.SessionLocal() as db:
            room = db.get(Room, self.room_id)
            occupancy = db.get(PositionOccupancy, occupancy_id)
            order = db.get(Order, checkout.json()["order_id"])
            service_order = db.get(ServiceOrder, service_order_id)
            feedback = db.scalar(select(ServiceFeedback).where(ServiceFeedback.selection_session_id == self.session_id))
            occupancy_actions = set(db.scalars(select(AuditLog.action).where(AuditLog.entity_id == str(occupancy_id))))
            self.assertEqual(order.status, "completed")
            self.assertEqual(service_order.status, "completed")
            self.assertEqual(room.status, "available")
            self.assertEqual(occupancy.status, "released")
            self.assertIsNotNone(occupancy.departed_at)
            self.assertIsNotNone(occupancy.released_at)
            self.assertIsNotNone(feedback)
            self.assertTrue({"confirm_departure", "finish_cleaning"}.issubset(occupancy_actions))


if __name__ == "__main__":
    unittest.main()
