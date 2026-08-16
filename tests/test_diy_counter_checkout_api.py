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
from app.models import AuditLog, CouponTemplate, Order, PositionOccupancy, PriceBook, Project, SelectionChangeRequest, SelectionRevision, SelectionSession, ServiceFeedback, ServiceLine, Staff, Store, User, UserCoupon
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

    def confirm_session_for_counter_checkout(self):
        with self.SessionLocal() as db:
            session = db.get(SelectionSession, self.session_id)
            service_line_id = "diy-counter-default-confirmed-line"
            revision_id = "diy-counter-default-confirmed-revision"
            confirmed_item = {
                **session.items[0],
                "service_line_id": service_line_id,
                "state": "confirmed",
            }
            session.status = "confirmed"
            session.items = [confirmed_item]
            revision = SelectionRevision(
                id=revision_id,
                selection_session_id=self.session_id,
                revision_no=1,
                state="confirmed",
                idempotency_key=revision_id,
                snapshot={"items": [confirmed_item], "pricing": session.pricing_snapshot},
            )
            db.add_all([
                revision,
                ServiceLine(
                    id=service_line_id,
                    selection_session_id=self.session_id,
                    selection_revision_id=revision_id,
                    snapshot=confirmed_item,
                    state="pending",
                ),
            ])
            db.commit()

    def grant_coupon(
        self,
        code,
        *,
        coupon_type="fixed",
        amount_cents=0,
        percent_off=None,
        min_spend_cents=0,
        status="unused",
        expire_at=None,
        user_id=None,
    ):
        with self.SessionLocal() as db:
            template = CouponTemplate(
                code=code,
                name=f"{code}优惠券",
                coupon_type=coupon_type,
                amount_cents=amount_cents,
                percent_off=percent_off,
                min_spend_cents=min_spend_cents,
                status="published",
            )
            db.add(template)
            db.flush()
            coupon = UserCoupon(
                user_id=user_id or self.customer_id,
                template_id=template.id,
                status=status,
                expire_at=expire_at,
            )
            db.add(coupon)
            db.commit()
            return coupon.id

    def prepare_completed_direct_selection(self, pricing):
        with self.SessionLocal() as db:
            session = db.get(SelectionSession, self.session_id)
            session.status = "confirmed"
            session.pricing_snapshot = pricing
            confirmed_item = {
                **session.items[0],
                "service_line_id": "automatic-coupon-direct-line",
                "state": "confirmed",
            }
            session.items = [confirmed_item]
            revision = SelectionRevision(
                id="automatic-coupon-direct-revision",
                selection_session_id=self.session_id,
                revision_no=1,
                state="confirmed",
                idempotency_key="automatic-coupon-direct-revision",
                snapshot={"items": [confirmed_item], "pricing": pricing},
            )
            db.add_all([
                revision,
                ServiceLine(
                    id="automatic-coupon-direct-line",
                    selection_session_id=self.session_id,
                    selection_revision_id=revision.id,
                    snapshot=confirmed_item,
                    state="completed",
                ),
            ])
            occupancy = db.scalar(select(PositionOccupancy).where(
                PositionOccupancy.selection_session_id == self.session_id,
            ))
            occupancy.status = "post_service_present"
            occupancy.actual_service_end_at = datetime.now(timezone.utc)
            db.commit()

    def checkout_and_finish_service(self, prefix):
        self.confirm_session_for_counter_checkout()
        checkout = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/counter-checkout",
            headers=self.headers,
            json={
                "idempotency_key": f"{prefix}-checkout",
                "payment_method": "cash",
                "received_amount_cents": 2990,
                "payment_reference": "",
            },
        )
        self.assertEqual(checkout.status_code, 200, checkout.text)
        checkout_data = checkout.json()
        assigned = self.client.post(
            f"/api/v1/operations/visits/{checkout_data['visit_id']}/assign",
            headers=self.headers,
            json={
                "idempotency_key": f"{prefix}-assign",
                "technician_id": self.technician_id,
                "room_id": self.room_id,
                "project_ids": [self.project_id],
            },
        )
        self.assertEqual(assigned.status_code, 200, assigned.text)
        for action in ("ready", "start", "finish"):
            response = self.client.post(
                f"/api/v1/operations/service-orders/{checkout_data['service_order_id']}/{action}",
                headers=self.headers,
                json={"idempotency_key": f"{prefix}-{action}"},
            )
            self.assertEqual(response.status_code, 200, response.text)
        return checkout_data

    def test_quote_previews_best_coupon_with_deterministic_tie_break_without_consuming_it(self):
        with self.SessionLocal() as db:
            db.get(User, self.customer_id).is_member = False
            other_customer = User(openid="automatic-coupon-other-customer")
            db.add_all([
                other_customer,
                PriceBook(project_id=self.project_id, price_type="store", amount_cents=3990),
                PriceBook(project_id=self.project_id, price_type="member", amount_cents=2990),
            ])
            db.commit()
            other_customer_id = other_customer.id

        earliest_expiry = datetime(2030, 1, 1, tzinfo=timezone.utc)
        selected_coupon_id = self.grant_coupon(
            "QUOTE-BEST-EARLIEST-FIRST",
            amount_cents=5000,
            expire_at=earliest_expiry,
        )
        same_expiry_later_id = self.grant_coupon(
            "QUOTE-BEST-EARLIEST-SECOND",
            amount_cents=5000,
            expire_at=earliest_expiry,
        )
        percent_coupon_id = self.grant_coupon(
            "QUOTE-BEST-PERCENT",
            coupon_type="percent",
            percent_off=30,
            expire_at=datetime(2031, 1, 1, tzinfo=timezone.utc),
        )
        expired_coupon_id = self.grant_coupon(
            "QUOTE-EXPIRED",
            amount_cents=5000,
            expire_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        locked_coupon_id = self.grant_coupon(
            "QUOTE-LOCKED",
            amount_cents=5000,
            status="locked",
            expire_at=datetime(2029, 1, 1, tzinfo=timezone.utc),
        )
        threshold_coupon_id = self.grant_coupon(
            "QUOTE-THRESHOLD",
            amount_cents=5000,
            min_spend_cents=4000,
            expire_at=datetime(2029, 1, 1, tzinfo=timezone.utc),
        )
        other_customer_coupon_id = self.grant_coupon(
            "QUOTE-OTHER-CUSTOMER",
            amount_cents=5000,
            expire_at=datetime(2029, 1, 1, tzinfo=timezone.utc),
            user_id=other_customer_id,
        )

        response = self.client.post(
            f"/api/v1/selection-sessions/{self.session_id}/quote",
            headers={"X-Selection-Token": "diy-counter-token"},
            json={"items": [{"project_id": self.project_id}]},
        )

        self.assertEqual(response.status_code, 200, response.text)
        preview = response.json().get("automatic_coupon")
        self.assertIsNotNone(preview)
        self.assertEqual(preview["coupon_id"], selected_coupon_id)
        self.assertEqual(preview["coupon_name"], "QUOTE-BEST-EARLIEST-FIRST优惠券")
        self.assertEqual(preview["discount_cents"], 1000)
        self.assertEqual(preview["payable_after_coupon_cents"], 2990)
        self.assertEqual(preview["member_floor_cents"], 2990)
        self.assertEqual(preview["expire_at"], earliest_expiry.isoformat())
        with self.SessionLocal() as db:
            for coupon_id in (
                selected_coupon_id,
                same_expiry_later_id,
                percent_coupon_id,
                expired_coupon_id,
                locked_coupon_id,
                threshold_coupon_id,
                other_customer_coupon_id,
            ):
                expected_status = "locked" if coupon_id == locked_coupon_id else "unused"
                self.assertEqual(db.get(UserCoupon, coupon_id).status, expected_status)

    def test_quote_keeps_coupon_unused_when_current_payable_is_at_member_floor(self):
        with self.SessionLocal() as db:
            db.add_all([
                PriceBook(project_id=self.project_id, price_type="store", amount_cents=3990),
                PriceBook(project_id=self.project_id, price_type="member", amount_cents=2990),
            ])
            db.commit()
        coupon_id = self.grant_coupon("QUOTE-AT-FLOOR", amount_cents=500)

        response = self.client.post(
            f"/api/v1/selection-sessions/{self.session_id}/quote",
            headers={"X-Selection-Token": "diy-counter-token"},
            json={"items": [{"project_id": self.project_id}]},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json().get("automatic_coupon"), {
            "coupon_id": None,
            "coupon_name": None,
            "template_id": None,
            "coupon_type": None,
            "raw_discount_cents": 0,
            "discount_cents": 0,
            "payable_after_coupon_cents": 2990,
            "member_floor_cents": 2990,
            "expire_at": None,
        })
        with self.SessionLocal() as db:
            self.assertEqual(db.get(UserCoupon, coupon_id).status, "unused")

    def test_direct_settlement_uses_best_small_fixed_coupon_once_and_audits_order(self):
        pricing = {
            "store_total_cents": 3990,
            "member_total_cents": 2990,
            "payable_total_cents": 3990,
            "lines": [{"project_id": self.project_id, "name": "草本泡脚", "quantity": 1}],
        }
        self.prepare_completed_direct_selection(pricing)
        selected_coupon_id = self.grant_coupon("DIRECT-FIXED-500", amount_cents=500)
        second_coupon_id = self.grant_coupon("DIRECT-FIXED-300", amount_cents=300)
        payload = {
            "idempotency_key": "automatic-coupon-direct-settle",
            "payment_method": "cash",
            "received_amount_cents": 3490,
            "payment_reference": "AUTOMATIC-COUPON-DIRECT-CASH",
        }

        response = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/settle",
            headers=self.headers,
            json=payload,
        )

        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["payable_total_cents"], 3490)
        self.assertEqual(result["automatic_coupon"]["coupon_id"], selected_coupon_id)
        self.assertEqual(result["automatic_coupon"]["discount_cents"], 500)
        replay = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/settle",
            headers=self.headers,
            json=payload,
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), result)
        with self.SessionLocal() as db:
            order = db.get(Order, result["order_id"])
            selected_coupon = db.get(UserCoupon, selected_coupon_id)
            self.assertEqual(order.total_amount_cents, 3990)
            self.assertEqual(order.pay_amount_cents, 3490)
            self.assertEqual(order.discount_cents, 500)
            self.assertEqual(order.coupon_id, selected_coupon_id)
            self.assertEqual(order.items[-1]["item_kind"], "automatic_coupon")
            self.assertEqual(order.items[-1]["discount_cents"], 500)
            self.assertEqual(selected_coupon.status, "used")
            self.assertEqual(selected_coupon.used_order_id, order.id)
            self.assertEqual(db.get(UserCoupon, second_coupon_id).status, "unused")

    def test_direct_settlement_caps_large_fixed_coupon_at_floor_and_rejects_short_payment(self):
        pricing = {
            "store_total_cents": 3990,
            "member_total_cents": 2990,
            "payable_total_cents": 3990,
            "lines": [{"project_id": self.project_id, "name": "草本泡脚", "quantity": 1}],
        }
        self.prepare_completed_direct_selection(pricing)
        coupon_id = self.grant_coupon("DIRECT-FIXED-LARGE", amount_cents=5000)

        insufficient = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/settle",
            headers=self.headers,
            json={
                "idempotency_key": "automatic-coupon-direct-short",
                "payment_method": "cash",
                "received_amount_cents": 2989,
            },
        )
        self.assertEqual(insufficient.status_code, 409, insufficient.text)
        self.assertEqual(insufficient.json()["detail"]["code"], "PAYMENT_NOT_CONFIRMED")
        with self.SessionLocal() as db:
            self.assertEqual(db.get(UserCoupon, coupon_id).status, "unused")
            self.assertIsNone(db.get(SelectionSession, self.session_id).fulfillment_order_id)

        settled = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/settle",
            headers=self.headers,
            json={
                "idempotency_key": "automatic-coupon-direct-floor",
                "payment_method": "cash",
                "received_amount_cents": 2990,
            },
        )
        self.assertEqual(settled.status_code, 200, settled.text)
        self.assertEqual(settled.json()["automatic_coupon"]["raw_discount_cents"], 5000)
        self.assertEqual(settled.json()["automatic_coupon"]["discount_cents"], 1000)
        self.assertEqual(settled.json()["payable_total_cents"], 2990)

    def test_service_settlement_reprices_percent_coupon_from_latest_confirmed_revision(self):
        checkout = self.checkout_and_finish_service("automatic-coupon-service")
        latest_pricing = {
            "store_total_cents": 9000,
            "member_total_cents": 6000,
            "payable_total_cents": 8000,
            "lines": [{
                "project_id": self.project_id,
                "name": "草本泡脚与服务中加选",
                "quantity": 2,
                "payable_line_total_cents": 8000,
            }],
        }
        with self.SessionLocal() as db:
            revision = db.scalar(select(SelectionRevision).where(
                SelectionRevision.selection_session_id == self.session_id,
                SelectionRevision.state == "confirmed",
            ).order_by(SelectionRevision.revision_no.desc()))
            revision.snapshot = {**revision.snapshot, "pricing": latest_pricing}
            order = db.get(Order, checkout["order_id"])
            service_order = db.get(ServiceOrder, checkout["service_order_id"])
            order.items = latest_pricing["lines"]
            order.total_amount_cents = 8000
            order.pay_amount_cents = 8000
            order.discount_cents = 1000
            service_order.items = latest_pricing["lines"]
            service_order.total_amount_cents = 8000
            db.commit()
        percent_coupon_id = self.grant_coupon(
            "SERVICE-PERCENT-25",
            coupon_type="percent",
            percent_off=25,
            min_spend_cents=7000,
        )
        fixed_coupon_id = self.grant_coupon(
            "SERVICE-FIXED-1500",
            amount_cents=1500,
            min_spend_cents=7000,
        )

        insufficient = self.client.post(
            f"/api/v1/operations/service-orders/{checkout['service_order_id']}/settle",
            headers=self.headers,
            json={
                "idempotency_key": "automatic-coupon-service-short",
                "payment_method": "cash",
                "received_amount_cents": 5999,
            },
        )
        self.assertEqual(insufficient.status_code, 409, insufficient.text)
        self.assertEqual(insufficient.json()["detail"]["code"], "PAYMENT_NOT_CONFIRMED")
        with self.SessionLocal() as db:
            self.assertEqual(db.get(UserCoupon, percent_coupon_id).status, "unused")
            self.assertEqual(db.get(Order, checkout["order_id"]).pay_amount_cents, 8000)

        settled = self.client.post(
            f"/api/v1/operations/service-orders/{checkout['service_order_id']}/settle",
            headers=self.headers,
            json={
                "idempotency_key": "automatic-coupon-service-final",
                "payment_method": "cash",
                "received_amount_cents": 6000,
                "payment_reference": "AUTOMATIC-COUPON-SERVICE-CASH",
            },
        )
        self.assertEqual(settled.status_code, 200, settled.text)
        result = settled.json()
        self.assertEqual(result["payable_total_cents"], 6000)
        self.assertEqual(result["automatic_coupon"]["coupon_id"], percent_coupon_id)
        self.assertEqual(result["automatic_coupon"]["raw_discount_cents"], 2000)
        self.assertEqual(result["automatic_coupon"]["discount_cents"], 2000)
        with self.SessionLocal() as db:
            order = db.get(Order, checkout["order_id"])
            service_order = db.get(ServiceOrder, checkout["service_order_id"])
            percent_coupon = db.get(UserCoupon, percent_coupon_id)
            self.assertEqual(order.total_amount_cents, 8000)
            self.assertEqual(order.pay_amount_cents, 6000)
            self.assertEqual(order.discount_cents, 3000)
            self.assertEqual(order.coupon_id, percent_coupon_id)
            self.assertEqual(order.items[-1]["item_kind"], "automatic_coupon")
            self.assertEqual(service_order.total_amount_cents, 6000)
            self.assertEqual(percent_coupon.status, "used")
            self.assertEqual(percent_coupon.used_order_id, order.id)
            self.assertEqual(db.get(UserCoupon, fixed_coupon_id).status, "unused")

    def test_counter_checkout_transfers_confirmed_service_flow_without_collecting_payment(self):
        self.confirm_session_for_counter_checkout()
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

    def test_service_time_addition_syncs_unsettled_bill_and_settlement_rejects_stale_snapshot(self):
        with self.SessionLocal() as db:
            db.add_all([
                PriceBook(project_id=self.project_id, price_type="store", amount_cents=4000),
                PriceBook(project_id=self.project_id, price_type="member", amount_cents=4000),
            ])
            db.commit()

        confirmed = self.client.post(
            f"/api/v1/admin/v2/selection-sessions/{self.session_id}/confirm",
            headers=self.headers,
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(confirmed.json()["pricing_snapshot"]["payable_total_cents"], 4000)

        checkout = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/counter-checkout",
            headers=self.headers,
            json={
                "idempotency_key": "addition-billing-checkout",
                "payment_method": "cash",
                "received_amount_cents": 4000,
                "payment_reference": "",
            },
        )
        self.assertEqual(checkout.status_code, 200, checkout.text)
        checkout_data = checkout.json()

        assigned = self.client.post(
            f"/api/v1/operations/visits/{checkout_data['visit_id']}/assign",
            headers=self.headers,
            json={
                "idempotency_key": "addition-billing-assign",
                "technician_id": self.technician_id,
                "room_id": self.room_id,
                "project_ids": [self.project_id],
            },
        )
        self.assertEqual(assigned.status_code, 200, assigned.text)
        ready = self.client.post(
            f"/api/v1/operations/service-orders/{checkout_data['service_order_id']}/ready",
            headers=self.headers,
            json={"idempotency_key": "addition-billing-ready"},
        )
        self.assertEqual(ready.status_code, 200, ready.text)
        started = self.client.post(
            f"/api/v1/operations/service-orders/{checkout_data['service_order_id']}/start",
            headers=self.headers,
            json={"idempotency_key": "addition-billing-start"},
        )
        self.assertEqual(started.status_code, 200, started.text)

        addition = self.client.post(
            f"/api/v1/selection-sessions/{self.session_id}/revisions",
            headers={
                "X-Selection-Token": "diy-counter-token",
                "Idempotency-Key": "addition-billing-request",
            },
            json={
                "items": [
                    {"project_id": self.project_id, "diy_preferences": ["暖泡舒缓"]},
                    {"project_id": self.project_id, "diy_preferences": ["加选腿部"]},
                ],
            },
        )
        self.assertEqual(addition.status_code, 200, addition.text)
        with self.SessionLocal() as db:
            change = db.scalar(select(SelectionChangeRequest).where(
                SelectionChangeRequest.selection_revision_id == addition.json()["id"],
            ))
            self.assertIsNotNone(change)
            change_id = change.id

        approved = self.client.post(
            f"/api/v1/admin/v2/selection-change-requests/{change_id}/approve",
            headers=self.headers,
        )
        self.assertEqual(approved.status_code, 200, approved.text)

        with self.SessionLocal() as db:
            revision = db.get(SelectionRevision, addition.json()["id"])
            order = db.get(Order, checkout_data["order_id"])
            service_order = db.get(ServiceOrder, checkout_data["service_order_id"])
            self.assertEqual(revision.snapshot["pricing"]["payable_total_cents"], 8000)
            self.assertEqual(order.total_amount_cents, 8000)
            self.assertEqual(order.pay_amount_cents, 8000)
            self.assertEqual(order.items, revision.snapshot["pricing"]["lines"])
            self.assertEqual(service_order.total_amount_cents, 8000)
            self.assertEqual(service_order.items, revision.snapshot["pricing"]["lines"])
            self.assertEqual(
                {item["service_line_id"] for item in revision.snapshot["items"]},
                {line.id for line in db.scalars(select(ServiceLine).where(
                    ServiceLine.selection_session_id == self.session_id,
                    ServiceLine.state != "cancelled",
                ))},
            )

        finished = self.client.post(
            f"/api/v1/operations/service-orders/{checkout_data['service_order_id']}/finish",
            headers=self.headers,
            json={"idempotency_key": "addition-billing-finish"},
        )
        self.assertEqual(finished.status_code, 200, finished.text)

        with self.SessionLocal() as db:
            order = db.get(Order, checkout_data["order_id"])
            service_order = db.get(ServiceOrder, checkout_data["service_order_id"])
            order.items = list(order.items[:1])
            order.total_amount_cents = 4000
            order.pay_amount_cents = 4000
            service_order.items = list(service_order.items[:1])
            service_order.total_amount_cents = 4000
            db.commit()

        stale = self.client.post(
            f"/api/v1/operations/service-orders/{checkout_data['service_order_id']}/settle",
            headers=self.headers,
            json={
                "idempotency_key": "addition-billing-stale-settle",
                "payment_method": "cash",
                "received_amount_cents": 8000,
                "payment_reference": "",
            },
        )
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(stale.json()["detail"]["code"], "FROZEN_BILLING_SNAPSHOT_MISMATCH")

        with self.SessionLocal() as db:
            revision = db.get(SelectionRevision, addition.json()["id"])
            frozen_items = list(revision.snapshot["pricing"]["lines"])
            frozen_amount = revision.snapshot["pricing"]["payable_total_cents"]
            order = db.get(Order, checkout_data["order_id"])
            service_order = db.get(ServiceOrder, checkout_data["service_order_id"])
            order.items = frozen_items
            order.total_amount_cents = frozen_amount
            order.pay_amount_cents = frozen_amount
            service_order.items = frozen_items
            service_order.total_amount_cents = frozen_amount
            db.commit()

        insufficient = self.client.post(
            f"/api/v1/operations/service-orders/{checkout_data['service_order_id']}/settle",
            headers=self.headers,
            json={
                "idempotency_key": "addition-billing-short-settle",
                "payment_method": "cash",
                "received_amount_cents": 4000,
                "payment_reference": "",
            },
        )
        self.assertEqual(insufficient.status_code, 409, insufficient.text)
        self.assertEqual(insufficient.json()["detail"]["code"], "PAYMENT_NOT_CONFIRMED")

        settled = self.client.post(
            f"/api/v1/operations/service-orders/{checkout_data['service_order_id']}/settle",
            headers=self.headers,
            json={
                "idempotency_key": "addition-billing-final-settle",
                "payment_method": "cash",
                "received_amount_cents": 8000,
                "payment_reference": "ADDITION-BILLING-CASH",
            },
        )
        self.assertEqual(settled.status_code, 200, settled.text)
        with self.SessionLocal() as db:
            order = db.get(Order, checkout_data["order_id"])
            service_order = db.get(ServiceOrder, checkout_data["service_order_id"])
            self.assertEqual(order.pay_amount_cents, 8000)
            self.assertEqual(order.pay_status, "paid")
            self.assertEqual(service_order.total_amount_cents, 8000)
            self.assertEqual(service_order.status, "completed")

    def test_service_completion_before_addition_approval_keeps_authoritative_snapshot_and_bill_unchanged(self):
        self.confirm_session_for_counter_checkout()
        checkout = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/counter-checkout",
            headers=self.headers,
            json={
                "idempotency_key": "completion-before-approval-checkout",
                "payment_method": "cash",
                "received_amount_cents": 2990,
                "payment_reference": "",
            },
        )
        self.assertEqual(checkout.status_code, 200, checkout.text)
        checkout_data = checkout.json()
        assigned = self.client.post(
            f"/api/v1/operations/visits/{checkout_data['visit_id']}/assign",
            headers=self.headers,
            json={
                "idempotency_key": "completion-before-approval-assign",
                "technician_id": self.technician_id,
                "room_id": self.room_id,
                "project_ids": [self.project_id],
            },
        )
        self.assertEqual(assigned.status_code, 200, assigned.text)
        for action in ("ready", "start"):
            response = self.client.post(
                f"/api/v1/operations/service-orders/{checkout_data['service_order_id']}/{action}",
                headers=self.headers,
                json={"idempotency_key": f"completion-before-approval-{action}"},
            )
            self.assertEqual(response.status_code, 200, response.text)

        addition = self.client.post(
            f"/api/v1/selection-sessions/{self.session_id}/revisions",
            headers={
                "X-Selection-Token": "diy-counter-token",
                "Idempotency-Key": "completion-before-approval-request",
            },
            json={
                "items": [
                    {"project_id": self.project_id, "diy_preferences": ["暖泡舒缓"]},
                    {"project_id": self.project_id, "diy_preferences": ["服务结束前请求的加选"]},
                ],
            },
        )
        self.assertEqual(addition.status_code, 200, addition.text)
        with self.SessionLocal() as db:
            change = db.scalar(select(SelectionChangeRequest).where(
                SelectionChangeRequest.selection_revision_id == addition.json()["id"],
            ))
            self.assertIsNotNone(change)
            change_id = change.id

        finished = self.client.post(
            f"/api/v1/operations/service-orders/{checkout_data['service_order_id']}/finish",
            headers=self.headers,
            json={"idempotency_key": "completion-before-approval-finish"},
        )
        self.assertEqual(finished.status_code, 200, finished.text)
        rejected = self.client.post(
            f"/api/v1/admin/v2/selection-change-requests/{change_id}/approve",
            headers=self.headers,
        )
        self.assertEqual(rejected.status_code, 409, rejected.text)

        with self.SessionLocal() as db:
            session = db.get(SelectionSession, self.session_id)
            change = db.get(SelectionChangeRequest, change_id)
            revision = db.get(SelectionRevision, addition.json()["id"])
            order = db.get(Order, checkout_data["order_id"])
            service_order = db.get(ServiceOrder, checkout_data["service_order_id"])
            active_lines = list(db.scalars(select(ServiceLine).where(
                ServiceLine.selection_session_id == self.session_id,
                ServiceLine.state != "cancelled",
            )))
            self.assertEqual(change.state, "awaiting_staff_confirmation")
            self.assertEqual(revision.state, "awaiting_staff_confirmation")
            self.assertEqual(len(active_lines), 1)
            self.assertEqual(session.items[0]["service_line_id"], active_lines[0].id)
            self.assertEqual(order.pay_amount_cents, 2990)
            self.assertEqual(service_order.total_amount_cents, 2990)

    def test_counter_checkout_rejects_submitted_preview_without_confirmation(self):
        response = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/counter-checkout",
            headers=self.headers,
            json={
                "idempotency_key": "reject-submitted-preview",
                "payment_method": "cash",
                "received_amount_cents": 2990,
                "payment_reference": "",
            },
        )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "OPERATION_STATE_CONFLICT")

    def test_counter_checkout_rejects_confirmed_session_without_confirmed_revision(self):
        with self.SessionLocal() as db:
            session = db.get(SelectionSession, self.session_id)
            session.status = "confirmed"
            db.commit()

        response = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/counter-checkout",
            headers=self.headers,
            json={
                "idempotency_key": "reject-missing-confirmed-revision",
                "payment_method": "cash",
                "received_amount_cents": 2990,
                "payment_reference": "",
            },
        )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "CONFIRMED_PRICING_REQUIRED")

    def test_legacy_submit_confirm_creates_authority_for_counter_checkout(self):
        with self.SessionLocal() as db:
            db.add_all([
                PriceBook(project_id=self.project_id, price_type="store", amount_cents=3990),
                PriceBook(project_id=self.project_id, price_type="member", amount_cents=2990),
            ])
            db.commit()
        created = self.client.post(
            "/api/v1/selection-sessions",
            json={
                "store_id": self.store_id,
                "source": "personal_qr",
                "device_label": "兼容提交顾客手机",
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        session_id = created.json()["session"]["id"]
        token = created.json()["access_token"]
        submitted = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/submit",
            headers={"X-Selection-Token": token},
            json={"items": [{"project_id": self.project_id}]},
        )
        self.assertEqual(submitted.status_code, 200, submitted.text)
        self.assertEqual(submitted.json()["status"], "submitted")

        confirmed = self.client.post(
            f"/api/v1/admin/v2/selection-sessions/{session_id}/confirm",
            headers=self.headers,
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(confirmed.json()["pricing_snapshot"]["payable_total_cents"], 3990)
        confirmed_retry = self.client.post(
            f"/api/v1/admin/v2/selection-sessions/{session_id}/confirm",
            headers=self.headers,
        )
        self.assertEqual(confirmed_retry.status_code, 200, confirmed_retry.text)
        self.assertEqual(confirmed_retry.json()["items"], confirmed.json()["items"])
        with self.SessionLocal() as db:
            revisions = db.query(SelectionRevision).filter_by(
                selection_session_id=session_id,
                state="confirmed",
            ).all()
            lines = db.query(ServiceLine).filter_by(selection_session_id=session_id).all()
            self.assertEqual(len(revisions), 1)
            self.assertEqual(len(lines), 1)
            revision = revisions[0]
            line = lines[0]
            self.assertEqual(revision.snapshot["items"][0]["service_line_id"], line.id)
            self.assertEqual(line.snapshot, revision.snapshot["items"][0])
            self.assertEqual(revision.snapshot["pricing"]["payable_total_cents"], 3990)

        checkout = self.client.post(
            f"/api/v1/operations/selection-sessions/{session_id}/counter-checkout",
            headers=self.headers,
            json={
                "idempotency_key": "legacy-submit-counter-checkout",
                "payment_method": "cash",
                "received_amount_cents": 3990,
                "payment_reference": "",
            },
        )

        self.assertEqual(checkout.status_code, 200, checkout.text)
        self.assertEqual(checkout.json()["payable_total_cents"], 3990)
        with self.SessionLocal() as db:
            order = db.get(Order, checkout.json()["order_id"])
            self.assertEqual(order.pay_status, "unpaid")
            self.assertEqual(order.pay_amount_cents, 3990)

    def test_counter_checkout_rejects_extra_service_line_outside_authoritative_snapshot(self):
        self.confirm_session_for_counter_checkout()
        with self.SessionLocal() as db:
            revision = db.query(SelectionRevision).filter_by(
                selection_session_id=self.session_id,
                state="confirmed",
            ).one()
            db.add(ServiceLine(
                id="diy-counter-orphan-active-line",
                selection_session_id=self.session_id,
                selection_revision_id=revision.id,
                snapshot={"project_id": self.project_id, "name": "快照外服务项"},
                state="pending",
            ))
            db.commit()

        response = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/counter-checkout",
            headers=self.headers,
            json={
                "idempotency_key": "reject-extra-service-line",
                "payment_method": "cash",
                "received_amount_cents": 2990,
                "payment_reference": "",
            },
        )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "SERVICE_LINE_SNAPSHOT_MISMATCH")

    def test_counter_checkout_rejects_missing_service_line_from_authoritative_snapshot(self):
        self.confirm_session_for_counter_checkout()
        with self.SessionLocal() as db:
            revision = db.query(SelectionRevision).filter_by(
                selection_session_id=self.session_id,
                state="confirmed",
            ).one()
            revision.snapshot = {
                **revision.snapshot,
                "items": [
                    *revision.snapshot["items"],
                    {
                        "project_id": self.project_id,
                        "name": "缺少执行行的服务项",
                        "service_line_id": "diy-counter-missing-active-line",
                        "state": "confirmed",
                    },
                ],
            }
            db.commit()

        response = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/counter-checkout",
            headers=self.headers,
            json={
                "idempotency_key": "reject-missing-service-line",
                "payment_method": "cash",
                "received_amount_cents": 2990,
                "payment_reference": "",
            },
        )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "SERVICE_LINE_SNAPSHOT_MISMATCH")

    def test_counter_checkout_rejects_latest_revision_without_its_service_lines(self):
        with self.SessionLocal() as db:
            session = db.get(SelectionSession, self.session_id)
            session.status = "confirmed"
            older_item = {
                **session.items[0],
                "service_line_id": "counter-stale-service-line",
                "state": "confirmed",
            }
            latest_item = {
                **session.items[0],
                "service_line_id": "counter-latest-missing-service-line",
                "state": "confirmed",
            }
            older = SelectionRevision(
                id="counter-older-confirmed-revision",
                selection_session_id=self.session_id,
                revision_no=1,
                state="confirmed",
                idempotency_key="counter-older-confirmed-revision",
                snapshot={"pricing": session.pricing_snapshot, "items": [older_item]},
            )
            latest = SelectionRevision(
                id="counter-latest-confirmed-revision",
                selection_session_id=self.session_id,
                revision_no=2,
                state="confirmed",
                idempotency_key="counter-latest-confirmed-revision",
                snapshot={"pricing": session.pricing_snapshot, "items": [latest_item]},
            )
            db.add_all([older, latest])
            db.flush()
            db.add(ServiceLine(
                id="counter-stale-service-line",
                selection_session_id=self.session_id,
                selection_revision_id=older.id,
                snapshot=older_item,
                state="pending",
            ))
            db.commit()

        response = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/counter-checkout",
            headers=self.headers,
            json={
                "idempotency_key": "reject-stale-service-lines",
                "payment_method": "cash",
                "received_amount_cents": 2990,
                "payment_reference": "",
            },
        )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "SERVICE_LINE_SNAPSHOT_MISMATCH")

    def test_counter_checkout_rejects_confirmed_revision_without_pricing(self):
        with self.SessionLocal() as db:
            session = db.get(SelectionSession, self.session_id)
            session.status = "confirmed"
            revision = SelectionRevision(
                id="counter-confirmed-without-pricing",
                selection_session_id=self.session_id,
                revision_no=1,
                state="confirmed",
                idempotency_key="counter-confirmed-without-pricing",
                snapshot={"items": session.items},
            )
            db.add(revision)
            db.flush()
            db.add(ServiceLine(
                id="counter-line-without-pricing",
                selection_session_id=self.session_id,
                selection_revision_id=revision.id,
                snapshot=session.items[0],
                state="pending",
            ))
            db.commit()

        response = self.client.post(
            f"/api/v1/operations/selection-sessions/{self.session_id}/counter-checkout",
            headers=self.headers,
            json={
                "idempotency_key": "reject-confirmed-without-pricing",
                "payment_method": "cash",
                "received_amount_cents": 2990,
                "payment_reference": "",
            },
        )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "CONFIRMED_PRICING_REQUIRED")

    def test_completed_diy_service_can_settle_without_technician_assignment(self):
        with self.SessionLocal() as db:
            session = db.get(SelectionSession, self.session_id)
            session.status = "confirmed"
            confirmed_item = {
                **session.items[0],
                "service_line_id": "direct-settlement-line",
                "state": "confirmed",
            }
            session.items = [confirmed_item]
            revision = SelectionRevision(
                id="direct-settlement-revision",
                selection_session_id=self.session_id,
                revision_no=1,
                state="confirmed",
                idempotency_key="direct-settlement-revision",
                snapshot={
                    "items": [confirmed_item],
                    "pricing": session.pricing_snapshot,
                },
            )
            db.add(revision)
            db.flush()
            db.add(ServiceLine(
                id="direct-settlement-line",
                selection_session_id=self.session_id,
                selection_revision_id=revision.id,
                snapshot=confirmed_item,
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

    def test_direct_settlement_rejects_service_line_set_outside_latest_revision(self):
        authoritative_line_id = "direct-settlement-authoritative-line"
        with self.SessionLocal() as db:
            session = db.get(SelectionSession, self.session_id)
            session.status = "confirmed"
            authoritative_item = {
                **session.items[0],
                "service_line_id": authoritative_line_id,
                "state": "confirmed",
            }
            revision = SelectionRevision(
                id="direct-settlement-mismatch-revision",
                selection_session_id=self.session_id,
                revision_no=1,
                state="confirmed",
                idempotency_key="direct-settlement-mismatch-revision",
                snapshot={"items": [authoritative_item], "pricing": session.pricing_snapshot},
            )
            db.add(revision)
            db.flush()
            db.add_all([
                ServiceLine(
                    id=authoritative_line_id,
                    selection_session_id=self.session_id,
                    selection_revision_id=revision.id,
                    snapshot=authoritative_item,
                    state="completed",
                ),
                ServiceLine(
                    id="direct-settlement-orphan-line",
                    selection_session_id=self.session_id,
                    selection_revision_id=revision.id,
                    snapshot={"project_id": self.project_id, "name": "快照外服务项"},
                    state="completed",
                ),
            ])
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
                "idempotency_key": "direct-settlement-mismatch",
                "payment_method": "cash",
                "received_amount_cents": 2990,
                "payment_reference": "",
            },
        )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "SERVICE_LINE_SNAPSHOT_MISMATCH")

    def test_diy_service_cannot_settle_before_service_completion(self):
        self.confirm_session_for_counter_checkout()

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
            confirmed_item = {
                **session.items[0],
                "service_line_id": "abnormal-settlement-line",
                "state": "confirmed",
            }
            session.items = [confirmed_item]
            revision = SelectionRevision(
                id="abnormal-settlement-revision",
                selection_session_id=self.session_id,
                revision_no=1,
                state="confirmed",
                idempotency_key="abnormal-settlement-revision",
                snapshot={"items": [confirmed_item], "pricing": session.pricing_snapshot},
            )
            db.add(revision)
            db.flush()
            db.add(ServiceLine(
                id="abnormal-settlement-line",
                selection_session_id=self.session_id,
                selection_revision_id=revision.id,
                snapshot=confirmed_item,
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
            confirmed_item = {
                **session.items[0],
                "service_line_id": "abnormal-adjusted-line",
                "state": "confirmed",
            }
            session.items = [confirmed_item]
            revision = SelectionRevision(
                id="abnormal-adjusted-revision",
                selection_session_id=self.session_id,
                revision_no=1,
                state="confirmed",
                idempotency_key="abnormal-adjusted-revision",
                snapshot={"items": [confirmed_item], "pricing": session.pricing_snapshot},
            )
            db.add(revision)
            db.flush()
            db.add(ServiceLine(
                id="abnormal-adjusted-line",
                selection_session_id=self.session_id,
                selection_revision_id=revision.id,
                snapshot=confirmed_item,
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
            session = db.get(SelectionSession, self.session_id)
            session.status = "confirmed"
            confirmed_item = {
                "project_id": self.project_id,
                "name": "草本泡脚",
                "quantity": 1,
                "service_line_id": "diy-counter-member-line",
                "state": "confirmed",
            }
            revision = SelectionRevision(
                id="diy-counter-revision-member",
                selection_session_id=self.session_id,
                revision_no=1,
                state="confirmed",
                idempotency_key="diy-counter-member-price",
                snapshot={
                    "items": [confirmed_item],
                    "pricing": {
                        "store_total_cents": 3990,
                        "member_total_cents": 2990,
                        "payable_total_cents": 2990,
                        "lines": [{
                            "project_id": self.project_id,
                            "name": "草本泡脚",
                            "quantity": 1,
                            "service_line_id": "diy-counter-member-line",
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
                snapshot=confirmed_item,
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
            session = db.get(SelectionSession, self.session_id)
            session.status = "confirmed"
            confirmed_item = {
                "project_id": self.project_id,
                "name": "草本泡脚",
                "quantity": 1,
                "service_line_id": "diy-counter-service-line",
                "state": "confirmed",
            }
            revision = SelectionRevision(
                id="diy-counter-service-line-revision",
                selection_session_id=self.session_id,
                revision_no=1,
                state="confirmed",
                idempotency_key="diy-counter-service-line-revision",
                snapshot={
                    "items": [confirmed_item],
                    "pricing": {
                        "store_total_cents": 3990,
                        "member_total_cents": 2990,
                        "payable_total_cents": 2990,
                        "lines": [{"project_id": self.project_id, "name": "草本泡脚", "quantity": 1, "service_line_id": "diy-counter-service-line"}],
                    },
                },
            )
            db.add(revision)
            db.add(ServiceLine(
                id="diy-counter-service-line",
                selection_session_id=self.session_id,
                selection_revision_id=revision.id,
                snapshot=confirmed_item,
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
        self.confirm_session_for_counter_checkout()
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
        self.confirm_session_for_counter_checkout()
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
        self.confirm_session_for_counter_checkout()
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
        self.confirm_session_for_counter_checkout()
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
        self.confirm_session_for_counter_checkout()
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
        self.confirm_session_for_counter_checkout()
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
            session = db.get(SelectionSession, self.session_id)
            session.status = "confirmed"
            confirmed_item = {
                "project_id": self.project_id,
                "name": "草本泡脚",
                "quantity": 1,
                "service_line_id": "diy-counter-closure-line",
                "state": "confirmed",
            }
            revision = SelectionRevision(
                id="diy-counter-closure-revision",
                selection_session_id=self.session_id,
                revision_no=1,
                state="confirmed",
                idempotency_key="diy-counter-closure-revision",
                snapshot={
                    "items": [confirmed_item],
                    "pricing": {
                        "store_total_cents": 3990,
                        "member_total_cents": 2990,
                        "payable_total_cents": 2990,
                        "lines": [{"project_id": self.project_id, "name": "草本泡脚", "quantity": 1, "service_line_id": "diy-counter-closure-line"}],
                    },
                },
            )
            db.add(revision)
            db.add(ServiceLine(
                id="diy-counter-closure-line",
                selection_session_id=self.session_id,
                selection_revision_id=revision.id,
                snapshot=confirmed_item,
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
