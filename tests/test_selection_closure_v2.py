import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.main import app
from app.api.admin import create_staff_token, hash_password
from app.models import Addon, CouponTemplate, PositionOccupancy, PriceBook, Project, SelectionChangeRequest, SelectionRevision, SelectionSession, ServiceLine, Staff, Store, User
from app.models.operations import Room


class SelectionClosureV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(bind=cls.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(cls.engine)
        with cls.SessionLocal() as db:
            store = Store(store_code="closure-v2-store", name="闭环测试门店", address="测试地址")
            db.add(store)
            db.flush()
            project = Project(
                store_id=store.id,
                code="CLOSURE-V2-FOOT",
                category="bath",
                name="草本泡脚",
                publication_status="published",
            )
            db.add(project)
            db.flush()
            db.add_all([
                PriceBook(project_id=project.id, price_type="store", amount_cents=3990),
                PriceBook(project_id=project.id, price_type="member", amount_cents=2990),
            ])
            staff = Staff(
                username="closure-v2-admin",
                password_hash=hash_password("pass"),
                name="测试前台",
                role="admin",
                store_id=store.id,
            )
            db.add(staff)
            db.commit()
            cls.store_id = store.id
            cls.project_id = project.id
            cls.staff_id = staff.id

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        app.dependency_overrides.clear()
        cls.engine.dispose()

    def create_session(self):
        response = self.client.post(
            "/api/v1/selection-sessions",
            json={"store_id": self.store_id, "source": "personal_qr", "device_label": "顾客手机"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        return data["session"]["id"], data["access_token"]

    def test_quote_uses_server_price_and_returns_optional_member_hint(self):
        session_id, token = self.create_session()
        with self.SessionLocal() as db:
            session = db.get(SelectionSession, session_id)
            anonymous = User(openid="anon_closure_quote")
            db.add(anonymous)
            db.flush()
            session.customer_id = anonymous.id
            db.commit()
        response = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/quote",
            headers={"X-Selection-Token": token},
            json={"items": [{"project_id": self.project_id, "chargeable": False}]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["pricing"]["store_total_cents"], 3990)
        self.assertEqual(data["pricing"]["member_total_cents"], 2990)
        self.assertEqual(data["saving_hint"]["kind"], "member")
        self.assertEqual(data["saving_hint"]["estimated_saving_cents"], 1000)

    def test_fixed_kit_is_detail_only_and_cannot_enter_customer_selection(self):
        with self.SessionLocal() as db:
            kit = Project(
                store_id=self.store_id,
                code="CLOSURE-V2-KIT",
                category="kit",
                name="固定调理套盒",
                publication_status="published",
            )
            db.add(kit)
            db.flush()
            db.add(PriceBook(project_id=kit.id, price_type="store", amount_cents=98000))
            db.commit()
            kit_id = kit.id
        session_id, token = self.create_session()

        response = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/quote",
            headers={"X-Selection-Token": token},
            json={"items": [{"project_id": kit_id}]},
        )

        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()["detail"], {
            "code": "DETAIL_ONLY_PROJECT",
            "message": "套盒仅供查看详情，不支持加入顾客选单",
        })

    def test_legacy_misclassified_taoke_kit_code_is_still_detail_only(self):
        with self.SessionLocal() as db:
            legacy_kit = Project(
                store_id=self.store_id,
                code="hxy-taoke-60",
                category="balance",
                name="功夫调理（历史误分类）",
                publication_status="published",
            )
            db.add(legacy_kit)
            db.flush()
            db.add(PriceBook(project_id=legacy_kit.id, price_type="store", amount_cents=98000))
            db.commit()
            legacy_kit_id = legacy_kit.id
        session_id, token = self.create_session()

        response = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/quote",
            headers={"X-Selection-Token": token},
            json={"items": [{"project_id": legacy_kit_id}]},
        )

        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()["detail"], {
            "code": "DETAIL_ONLY_PROJECT",
            "message": "套盒仅供查看详情，不支持加入顾客选单",
        })

    def test_submit_revision_is_idempotent_and_allows_a_second_revision(self):
        session_id, token = self.create_session()
        headers = {"X-Selection-Token": token, "Idempotency-Key": "revision-one"}
        first_payload = {"items": [{"project_id": self.project_id}]}
        first = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/revisions",
            headers=headers,
            json=first_payload,
        )
        retry = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/revisions",
            headers=headers,
            json=first_payload,
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(first.json()["id"], retry.json()["id"])
        self.assertEqual(first.json()["revision_no"], 1)

        second = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/revisions",
            headers={"X-Selection-Token": token, "Idempotency-Key": "revision-two"},
            json={"items": [{"project_id": self.project_id, "diy_preferences": ["肩颈"]}]},
        )
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["revision_no"], 2)
        with self.SessionLocal() as db:
            session = db.get(SelectionSession, session_id)
            self.assertEqual(session.status, "submitted")
            self.assertEqual(session.items[0]["diy_preferences"], ["肩颈"])

    def test_quote_falls_back_to_claimable_coupon_hint_when_member_price_is_equal(self):
        session_id, token = self.create_session()
        with self.SessionLocal() as db:
            equal_project = Project(
                store_id=self.store_id,
                code="CLOSURE-V2-EQUAL",
                category="bath",
                name="同价项目",
                publication_status="published",
            )
            db.add(equal_project)
            db.flush()
            db.add_all([
                PriceBook(project_id=equal_project.id, price_type="store", amount_cents=3990),
                PriceBook(project_id=equal_project.id, price_type="member", amount_cents=3990),
            ])
            db.add(CouponTemplate(
                code="closure-v2-coupon",
                name="到店礼券",
                amount_cents=500,
                min_spend_cents=3000,
                is_claimable=True,
                status="published",
            ))
            db.commit()
        response = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/quote",
            headers={"X-Selection-Token": token},
            json={"items": [{"project_id": equal_project.id}]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["saving_hint"], {"kind": "coupon", "login_required": True})

    def test_quote_prices_structured_addon_with_member_rule(self):
        session_id, token = self.create_session()
        with self.SessionLocal() as db:
            addon = Addon(
                store_id=self.store_id,
                code="closure-v2-addon",
                name="局部加强",
                parent_project_id=self.project_id,
                store_price_cents=1200,
                member_price_cents=800,
                member_price_enabled=True,
                independently_sellable=True,
                can_attach_to_parent=True,
                publication_status="published",
                price_cents=1200,
            )
            db.add(addon)
            db.commit()
            addon_id = addon.id
        response = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/quote",
            headers={"X-Selection-Token": token},
            json={"items": [{"project_id": self.project_id, "addon_ids": [addon_id]}]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        pricing = response.json()["pricing"]
        self.assertEqual(pricing["store_total_cents"], 5190)
        self.assertEqual(pricing["member_total_cents"], 3790)

    def test_admin_can_publish_priced_and_free_addons_for_customer_catalog(self):
        headers = {"Authorization": f"Bearer {create_staff_token(self.staff_id, 'admin')}"}
        priced = self.client.post(
            "/api/v1/admin/v2/addons",
            headers=headers,
            json={
                "store_id": self.store_id,
                "code": "closure-v2-admin-priced",
                "name": "肩颈局部加强",
                "parent_project_id": self.project_id,
                "summary": "适合需要加强肩颈放松的顾客",
                "store_price_cents": 1200,
                "member_price_cents": 800,
                "member_price_enabled": True,
                "independently_sellable": True,
                "can_attach_to_parent": True,
                "publication_status": "draft",
            },
        )
        self.assertEqual(priced.status_code, 200, priced.text)
        priced_id = priced.json()["id"]
        self.assertTrue(priced.json()["chargeable"])

        free = self.client.post(
            "/api/v1/admin/v2/addons",
            headers=headers,
            json={
                "store_id": self.store_id,
                "code": "closure-v2-admin-free",
                "name": "热敷偏好",
                "parent_project_id": self.project_id,
                "chargeable": False,
                "store_price_cents": 0,
                "independently_sellable": False,
                "can_attach_to_parent": True,
                "publication_status": "published",
            },
        )
        self.assertEqual(free.status_code, 200, free.text)
        self.assertFalse(free.json()["chargeable"])

        hidden = self.client.get(f"/api/v1/addons?store_id={self.store_id}&parent_project_id={self.project_id}")
        self.assertEqual(hidden.status_code, 200, hidden.text)
        self.assertNotIn(priced_id, [item["id"] for item in hidden.json()])

        published = self.client.post(
            f"/api/v1/admin/v2/addons/{priced_id}",
            headers=headers,
            json={"publication_status": "published"},
        )
        self.assertEqual(published.status_code, 200, published.text)
        catalog = self.client.get(
            f"/api/v1/addons?store_id={self.store_id}&parent_project_id={self.project_id}&sale_mode=attach"
        )
        self.assertEqual(catalog.status_code, 200, catalog.text)
        catalog_item = next(item for item in catalog.json() if item["id"] == priced_id)
        self.assertTrue(catalog_item["chargeable"])
        self.assertEqual(catalog_item["prices"], {"store": 1200, "member": 800})
        self.assertEqual(catalog_item["summary"], "适合需要加强肩颈放松的顾客")

    def test_independently_sellable_addon_can_be_quoted_as_a_service(self):
        session_id, token = self.create_session()
        with self.SessionLocal() as db:
            addon = Addon(
                store_id=self.store_id,
                code="closure-v2-standalone-addon",
                name="肩颈局部加强",
                store_price_cents=1200,
                member_price_cents=800,
                member_price_enabled=True,
                independently_sellable=True,
                can_attach_to_parent=False,
                publication_status="published",
                price_cents=1200,
            )
            db.add(addon)
            db.commit()
            addon_id = addon.id

        response = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/quote",
            headers={"X-Selection-Token": token},
            json={"items": [{"addon_id": addon_id}]},
        )

        self.assertEqual(response.status_code, 200, response.text)
        item = response.json()["items"][0]
        self.assertEqual(item["item_kind"], "standalone_addon")
        self.assertEqual(item["name"], "肩颈局部加强")
        self.assertEqual(response.json()["pricing"]["store_total_cents"], 1200)
        self.assertEqual(response.json()["pricing"]["member_total_cents"], 800)

    def test_in_service_submission_waits_for_front_desk_confirmation(self):
        session_id, token = self.create_session()
        with self.SessionLocal() as db:
            db.add(PositionOccupancy(
                store_id=self.store_id,
                room_id=1,
                selection_session_id=session_id,
                active_session_id=session_id,
                status="in_service",
                source="personal_qr",
            ))
            db.commit()

        response = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/revisions",
            headers={"X-Selection-Token": token, "Idempotency-Key": "during-service"},
            json={"items": [{"project_id": self.project_id}]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["state"], "awaiting_staff_confirmation")
        with self.SessionLocal() as db:
            change = db.query(SelectionChangeRequest).filter_by(selection_session_id=session_id).order_by(SelectionChangeRequest.id.desc()).first()
            self.assertIsNotNone(change)
            self.assertEqual(change.state, "awaiting_staff_confirmation")

    def test_initial_revision_submission_moves_a_held_position_to_waiting_service(self):
        session_id, token = self.create_session()
        with self.SessionLocal() as db:
            db.add(PositionOccupancy(
                store_id=self.store_id,
                room_id=8,
                selection_session_id=session_id,
                active_session_id=session_id,
                status="held",
                source="personal_qr",
            ))
            db.commit()

        response = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/revisions",
            headers={"X-Selection-Token": token, "Idempotency-Key": "initial-revision-moves-position"},
            json={"items": [{"project_id": self.project_id}]},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["state"], "submitted")
        with self.SessionLocal() as db:
            session = db.get(SelectionSession, session_id)
            occupancy = db.query(PositionOccupancy).filter_by(selection_session_id=session_id).one()
            self.assertEqual(session.status, "submitted")
            self.assertEqual(occupancy.status, "waiting_service")
            self.assertIsNone(occupancy.hold_expires_at)

    def test_confirmed_session_allows_service_time_addition_for_front_desk_approval(self):
        session_id, token = self.create_session()
        with self.SessionLocal() as db:
            session = db.get(SelectionSession, session_id)
            session.status = "confirmed"
            db.add(PositionOccupancy(
                store_id=self.store_id,
                room_id=1,
                selection_session_id=session_id,
                active_session_id=session_id,
                status="in_service",
                source="personal_qr",
            ))
            db.commit()

        response = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/revisions",
            headers={"X-Selection-Token": token, "Idempotency-Key": "confirmed-during-service"},
            json={"items": [{"project_id": self.project_id}]},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["state"], "awaiting_staff_confirmation")
        with self.SessionLocal() as db:
            self.assertEqual(db.get(SelectionSession, session_id).status, "confirmed")

    def test_confirmed_selection_rejects_additions_outside_in_service(self):
        for status in ("waiting_service", "post_service_present", "cleaning", "released"):
            with self.subTest(occupancy_status=status):
                session_id, token = self.create_session()
                with self.SessionLocal() as db:
                    session = db.get(SelectionSession, session_id)
                    session.status = "confirmed"
                    db.add(PositionOccupancy(
                        store_id=self.store_id,
                        room_id=1,
                        selection_session_id=session_id,
                        active_session_id=session_id if status != "released" else None,
                        status=status,
                        source="personal_qr",
                    ))
                    db.commit()

                response = self.client.post(
                    f"/api/v1/selection-sessions/{session_id}/revisions",
                    headers={"X-Selection-Token": token, "Idempotency-Key": f"confirmed-{status}"},
                    json={"items": [{"project_id": self.project_id}]},
                )

                self.assertEqual(response.status_code, 409, response.text)

    def test_submitted_selection_rejects_additions_after_cleaning_or_release(self):
        for status in ("cleaning", "released"):
            with self.subTest(occupancy_status=status):
                session_id, token = self.create_session()
                with self.SessionLocal() as db:
                    db.add(PositionOccupancy(
                        store_id=self.store_id,
                        room_id=6,
                        selection_session_id=session_id,
                        active_session_id=session_id if status == "cleaning" else None,
                        status=status,
                        source="personal_qr",
                    ))
                    db.commit()

                response = self.client.post(
                    f"/api/v1/selection-sessions/{session_id}/revisions",
                    headers={"X-Selection-Token": token, "Idempotency-Key": f"submitted-{status}"},
                    json={"items": [{"project_id": self.project_id}]},
                )

                self.assertEqual(response.status_code, 409, response.text)

    def test_post_service_present_rejects_customer_additions(self):
        session_id, token = self.create_session()
        with self.SessionLocal() as db:
            db.add(PositionOccupancy(
                store_id=self.store_id,
                room_id=1,
                selection_session_id=session_id,
                active_session_id=session_id,
                status="post_service_present",
                source="personal_qr",
            ))
            db.commit()

        response = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/revisions",
            headers={"X-Selection-Token": token, "Idempotency-Key": "after-service"},
            json={"items": [{"project_id": self.project_id}]},
        )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"], "当前服务已结束，不能继续加选")

    def test_front_desk_approval_creates_actual_service_lines(self):
        session_id, token = self.create_session()
        with self.SessionLocal() as db:
            db.add(PositionOccupancy(
                store_id=self.store_id,
                room_id=2,
                selection_session_id=session_id,
                active_session_id=session_id,
                status="waiting_service",
                source="personal_qr",
            ))
            db.commit()
        first = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/revisions",
            headers={"X-Selection-Token": token, "Idempotency-Key": "before-service"},
            json={"items": [{"project_id": self.project_id, "diy_preferences": ["肩颈"]}]},
        )
        self.assertEqual(first.status_code, 200, first.text)
        with self.SessionLocal() as db:
            occupancy = db.query(PositionOccupancy).filter_by(selection_session_id=session_id).one()
            occupancy.status = "in_service"
            db.commit()
        self.client.post(
            f"/api/v1/selection-sessions/{session_id}/revisions",
            headers={"X-Selection-Token": token, "Idempotency-Key": "approval-source"},
            json={"items": [{"project_id": self.project_id, "diy_preferences": ["肩颈"]}, {"project_id": self.project_id, "diy_preferences": ["腿部"]}]},
        )
        with self.SessionLocal() as db:
            change = db.query(SelectionChangeRequest).filter_by(selection_session_id=session_id).order_by(SelectionChangeRequest.id.desc()).first()
            self.assertIsNotNone(change)
        response = self.client.post(
            f"/api/v1/admin/v2/selection-change-requests/{change.id}/approve",
            headers={"Authorization": f"Bearer {create_staff_token(self.staff_id, 'admin')}"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["state"], "approved")
        self.assertEqual(len(response.json()["service_lines"]), 1)
        self.assertEqual(response.json()["service_lines"][0]["snapshot"]["diy_preferences"], ["腿部"])

    def test_pending_or_rejected_service_time_addition_does_not_change_confirmed_selection(self):
        session_id, token = self.create_session()
        baseline_item = {
            "project_id": self.project_id,
            "name": "草本泡脚",
            "code": "CLOSURE-V2-FOOT",
            "quantity": 1,
            "item_type": "service",
            "chargeable": True,
            "diy_preferences": ["肩颈"],
        }
        baseline_pricing = {
            "store_total_cents": 3990,
            "member_total_cents": 2990,
            "payable_total_cents": 3990,
            "lines": [baseline_item],
        }
        with self.SessionLocal() as db:
            session = db.get(SelectionSession, session_id)
            session.status = "confirmed"
            session.items = [baseline_item]
            session.diy_preferences = {"note": "仅肩颈"}
            session.pricing_snapshot = baseline_pricing
            session.store_total_cents = 3990
            session.member_total_cents = 2990
            db.add(SelectionRevision(
                id=session_id,
                selection_session_id=session_id,
                revision_no=1,
                state="confirmed",
                idempotency_key=f"baseline-{session_id}",
                snapshot={"items": [baseline_item], "pricing": baseline_pricing},
            ))
            db.add(PositionOccupancy(
                store_id=self.store_id,
                room_id=3,
                selection_session_id=session_id,
                active_session_id=session_id,
                status="in_service",
                source="personal_qr",
            ))
            db.commit()

        submitted = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/revisions",
            headers={"X-Selection-Token": token, "Idempotency-Key": "pending-does-not-overwrite"},
            json={"items": [
                {"project_id": self.project_id, "diy_preferences": ["肩颈"]},
                {"project_id": self.project_id, "diy_preferences": ["腿部"]},
            ], "diy_preferences": {"note": "申请增加腿部"}},
        )
        self.assertEqual(submitted.status_code, 200, submitted.text)
        self.assertEqual(submitted.json()["state"], "awaiting_staff_confirmation")
        with self.SessionLocal() as db:
            session = db.get(SelectionSession, session_id)
            change = db.query(SelectionChangeRequest).filter_by(selection_session_id=session_id).one()
            self.assertEqual(session.items, [baseline_item])
            self.assertEqual(session.diy_preferences, {"note": "仅肩颈"})
            self.assertEqual(session.pricing_snapshot, baseline_pricing)

        rejected = self.client.post(
            f"/api/v1/admin/v2/selection-change-requests/{change.id}/reject",
            headers={"Authorization": f"Bearer {create_staff_token(self.staff_id, 'admin')}"},
            json={"reason": "当前时段无法增加"},
        )
        self.assertEqual(rejected.status_code, 200, rejected.text)
        with self.SessionLocal() as db:
            session = db.get(SelectionSession, session_id)
            self.assertEqual(session.items, [baseline_item])
            self.assertEqual(session.diy_preferences, {"note": "仅肩颈"})
            self.assertEqual(session.pricing_snapshot, baseline_pricing)

    def test_approving_service_time_addition_promotes_its_snapshot_to_confirmed_selection(self):
        session_id, token = self.create_session()
        baseline_item = {
            "project_id": self.project_id,
            "name": "草本泡脚",
            "code": "CLOSURE-V2-FOOT",
            "quantity": 1,
            "item_type": "service",
            "chargeable": True,
            "diy_preferences": ["肩颈"],
        }
        baseline_pricing = {
            "store_total_cents": 3990,
            "member_total_cents": 2990,
            "payable_total_cents": 3990,
            "lines": [baseline_item],
        }
        with self.SessionLocal() as db:
            session = db.get(SelectionSession, session_id)
            session.status = "confirmed"
            session.items = [baseline_item]
            session.diy_preferences = {"note": "仅肩颈"}
            session.pricing_snapshot = baseline_pricing
            session.store_total_cents = 3990
            session.member_total_cents = 2990
            db.add(SelectionRevision(
                id=session_id,
                selection_session_id=session_id,
                revision_no=1,
                state="confirmed",
                idempotency_key=f"baseline-{session_id}",
                snapshot={"items": [baseline_item], "pricing": baseline_pricing},
            ))
            db.add(PositionOccupancy(
                store_id=self.store_id,
                room_id=4,
                selection_session_id=session_id,
                active_session_id=session_id,
                status="in_service",
                source="personal_qr",
            ))
            db.commit()

        submitted = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/revisions",
            headers={"X-Selection-Token": token, "Idempotency-Key": "approval-promotes-snapshot"},
            json={"items": [
                {"project_id": self.project_id, "diy_preferences": ["肩颈"]},
                {"project_id": self.project_id, "diy_preferences": ["腿部"]},
            ], "diy_preferences": {"note": "已同意增加腿部"}},
        )
        self.assertEqual(submitted.status_code, 200, submitted.text)
        with self.SessionLocal() as db:
            change = db.query(SelectionChangeRequest).filter_by(selection_session_id=session_id).one()

        approved = self.client.post(
            f"/api/v1/admin/v2/selection-change-requests/{change.id}/approve",
            headers={"Authorization": f"Bearer {create_staff_token(self.staff_id, 'admin')}"},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        with self.SessionLocal() as db:
            session = db.get(SelectionSession, session_id)
            revision = db.get(SelectionRevision, submitted.json()["id"])
            self.assertEqual(session.status, "confirmed")
            self.assertEqual(len(session.items), 2)
            self.assertEqual(session.items[1]["diy_preferences"], ["腿部"])
            self.assertEqual(session.diy_preferences, {"note": "已同意增加腿部"})
            self.assertEqual(session.pricing_snapshot, revision.snapshot["pricing"])
            self.assertEqual(session.store_total_cents, revision.snapshot["pricing"]["store_total_cents"])
            self.assertEqual(session.member_total_cents, revision.snapshot["pricing"]["member_total_cents"])

    def test_position_service_actions_update_confirmed_service_lines(self):
        session_id, token = self.create_session()
        with self.SessionLocal() as db:
            db.add(PositionOccupancy(
                store_id=self.store_id,
                room_id=7,
                selection_session_id=session_id,
                active_room_id=7,
                active_session_id=session_id,
                status="held",
                source="personal_qr",
            ))
            db.commit()

        revision = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/revisions",
            headers={"X-Selection-Token": token, "Idempotency-Key": "position-actions-confirmed-line"},
            json={"items": [{"project_id": self.project_id}]},
        )
        self.assertEqual(revision.status_code, 200, revision.text)
        headers = {"Authorization": f"Bearer {create_staff_token(self.staff_id, 'admin')}"}
        confirmed = self.client.post(
            f"/api/v1/admin/v2/selection-sessions/{session_id}/confirm",
            headers=headers,
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        with self.SessionLocal() as db:
            occupancy = db.query(PositionOccupancy).filter_by(selection_session_id=session_id).one()
            line = db.query(ServiceLine).filter_by(selection_session_id=session_id).one()
            self.assertEqual(occupancy.status, "waiting_service")
            self.assertLessEqual(len(line.id), 36)
            self.assertEqual(line.state, "pending")
            occupancy_id = occupancy.id

        started = self.client.post(
            f"/api/v1/admin/occupancies/{occupancy_id}/start-service",
            headers=headers,
            json={"expected_minutes": 30},
        )
        self.assertEqual(started.status_code, 200, started.text)
        with self.SessionLocal() as db:
            line = db.query(ServiceLine).filter_by(selection_session_id=session_id).one()
            self.assertEqual(line.state, "in_service")
            self.assertIsNotNone(line.started_at)

        finished = self.client.post(
            f"/api/v1/admin/occupancies/{occupancy_id}/finish-service",
            headers=headers,
            json={},
        )
        self.assertEqual(finished.status_code, 200, finished.text)
        with self.SessionLocal() as db:
            line = db.query(ServiceLine).filter_by(selection_session_id=session_id).one()
            self.assertEqual(line.state, "completed")
            self.assertIsNotNone(line.completed_at)

    def test_front_desk_cannot_approve_addition_after_service_ended(self):
        session_id, token = self.create_session()
        with self.SessionLocal() as db:
            room = Room(
                store_id=self.store_id,
                code=f"ABNORMAL-{session_id[:8]}",
                name="异常结束测试沙发",
                room_type="sofa",
                status="available",
            )
            db.add(room)
            db.flush()
            db.add(PositionOccupancy(
                store_id=self.store_id,
                room_id=room.id,
                active_room_id=room.id,
                selection_session_id=session_id,
                active_session_id=session_id,
                status="in_service",
                source="personal_qr",
            ))
            db.commit()
        submitted = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/revisions",
            headers={"X-Selection-Token": token, "Idempotency-Key": "stale-approval"},
            json={"items": [{"project_id": self.project_id}]},
        )
        self.assertEqual(submitted.status_code, 200, submitted.text)
        with self.SessionLocal() as db:
            occupancy = db.query(PositionOccupancy).filter_by(selection_session_id=session_id).one()
            occupancy.status = "post_service_present"
            db.commit()
            change = db.query(SelectionChangeRequest).filter_by(selection_session_id=session_id).one()

        response = self.client.post(
            f"/api/v1/admin/v2/selection-change-requests/{change.id}/approve",
            headers={"Authorization": f"Bearer {create_staff_token(self.staff_id, 'admin')}"},
        )

        self.assertEqual(response.status_code, 409, response.text)
        with self.SessionLocal() as db:
            self.assertEqual(db.get(SelectionChangeRequest, change.id).state, "awaiting_staff_confirmation")
            self.assertEqual(db.query(ServiceLine).filter_by(selection_session_id=session_id).count(), 0)

    def test_abnormal_service_end_rejects_pending_addition(self):
        session_id, token = self.create_session()
        with self.SessionLocal() as db:
            room = Room(
                store_id=self.store_id,
                code=f"FORCE-{session_id[:8]}",
                name="强制结束测试沙发",
                room_type="sofa",
                status="available",
            )
            db.add(room)
            db.flush()
            db.add(PositionOccupancy(
                store_id=self.store_id,
                room_id=room.id,
                active_room_id=room.id,
                selection_session_id=session_id,
                active_session_id=session_id,
                status="in_service",
                source="personal_qr",
            ))
            db.commit()
        submitted = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/revisions",
            headers={"X-Selection-Token": token, "Idempotency-Key": "abnormal-end-addition"},
            json={"items": [{"project_id": self.project_id}]},
        )
        self.assertEqual(submitted.status_code, 200, submitted.text)
        with self.SessionLocal() as db:
            occupancy = db.query(PositionOccupancy).filter_by(selection_session_id=session_id).one()
            change = db.query(SelectionChangeRequest).filter_by(selection_session_id=session_id).one()

        response = self.client.post(
            f"/api/v1/admin/occupancies/{occupancy.id}/force-release",
            headers={"Authorization": f"Bearer {create_staff_token(self.staff_id, 'admin')}"},
            json={
                "reason_code": "service_aborted",
                "target_state": "cleaning",
                "reason": "顾客身体不适，服务异常结束",
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "cleaning")
        with self.SessionLocal() as db:
            self.assertEqual(db.get(SelectionChangeRequest, change.id).state, "rejected")
            self.assertEqual(db.get(SelectionChangeRequest, change.id).reason, "服务位异常结束：顾客身体不适，服务异常结束")
            self.assertEqual(db.get(SelectionRevision, submitted.json()["id"]).state, "rejected")

    def test_front_desk_can_reject_addition_with_reason_without_creating_service_lines(self):
        session_id, token = self.create_session()
        with self.SessionLocal() as db:
            db.add(PositionOccupancy(
                store_id=self.store_id,
                room_id=4,
                selection_session_id=session_id,
                active_session_id=session_id,
                status="in_service",
                source="personal_qr",
            ))
            db.commit()
        submitted = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/revisions",
            headers={"X-Selection-Token": token, "Idempotency-Key": "reject-addition"},
            json={"items": [{"project_id": self.project_id}]},
        )
        self.assertEqual(submitted.status_code, 200, submitted.text)
        with self.SessionLocal() as db:
            change = db.query(SelectionChangeRequest).filter_by(selection_session_id=session_id).one()

        response = self.client.post(
            f"/api/v1/admin/v2/selection-change-requests/{change.id}/reject",
            headers={"Authorization": f"Bearer {create_staff_token(self.staff_id, 'admin')}"},
            json={"reason": "当前服务时长不足，无法安排该项目"},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"id": change.id, "state": "rejected", "reason": "当前服务时长不足，无法安排该项目"})
        with self.SessionLocal() as db:
            self.assertEqual(db.get(SelectionChangeRequest, change.id).state, "rejected")
            self.assertEqual(db.get(SelectionRevision, submitted.json()["id"]).state, "rejected")
            self.assertEqual(db.query(ServiceLine).filter_by(selection_session_id=session_id).count(), 0)

    def test_rejecting_addition_requires_a_reason(self):
        session_id, token = self.create_session()
        with self.SessionLocal() as db:
            db.add(PositionOccupancy(
                store_id=self.store_id,
                room_id=5,
                selection_session_id=session_id,
                active_session_id=session_id,
                status="in_service",
                source="personal_qr",
            ))
            db.commit()
        submitted = self.client.post(
            f"/api/v1/selection-sessions/{session_id}/revisions",
            headers={"X-Selection-Token": token, "Idempotency-Key": "reject-reason-required"},
            json={"items": [{"project_id": self.project_id}]},
        )
        self.assertEqual(submitted.status_code, 200, submitted.text)
        with self.SessionLocal() as db:
            change = db.query(SelectionChangeRequest).filter_by(selection_session_id=session_id).one()

        response = self.client.post(
            f"/api/v1/admin/v2/selection-change-requests/{change.id}/reject",
            headers={"Authorization": f"Bearer {create_staff_token(self.staff_id, 'admin')}"},
            json={"reason": "  "},
        )

        self.assertEqual(response.status_code, 400, response.text)


if __name__ == "__main__":
    unittest.main()
