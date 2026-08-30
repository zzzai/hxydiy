from datetime import date, timedelta, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import AuditLog, Order, PositionOccupancy, SelectionSession, Staff, Store, User, Project, PriceBook
from app.models.operations import Room, Technician
from app.models.service import ServiceAssignment, ServiceOrder, Visit


class TestTechnicianPortalApi:
    def setup_method(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        with self.SessionLocal() as db:
            store = Store(store_code="tech-portal-store", name="技师端测试店", address="测试地址")
            db.add(store)
            db.flush()
            admin = Staff(
                username="tech-portal-admin",
                password_hash=hash_password("admin-pass"),
                name="测试店长",
                role="admin",
                status="active",
                store_id=store.id,
            )
            technician = Technician(
                store_id=store.id,
                code="TECH-PORTAL-1",
                name="小悦技师",
                status="available",
            )
            db.add_all([admin, technician])
            db.commit()
            self.store_id = store.id
            self.admin_id = admin.id
            self.technician_id = technician.id
        app.dependency_overrides[get_db] = self._override_get_db
        self.client = TestClient(app)
        self.admin_headers = {
            "Authorization": f"Bearer {create_staff_token(self.admin_id, 'admin')}"
        }

    def teardown_method(self):
        app.dependency_overrides.clear()
        self.client.close()
        self.engine.dispose()

    def _override_get_db(self):
        with self.SessionLocal() as db:
            yield db

    def test_admin_invites_technician_and_activation_creates_login_account(self):
        invite = self.client.post(
            f"/api/v1/admin/v2/technicians/{self.technician_id}/invite",
            headers=self.admin_headers,
        )
        assert invite.status_code == 200, invite.text
        payload = invite.json()
        assert payload["technician_id"] == self.technician_id
        assert payload["token"]

        activated = self.client.post(
            "/api/v1/technician/activate",
            json={"token": payload["token"], "password": "tech-pass-123"},
        )
        assert activated.status_code == 200, activated.text
        assert activated.json()["staff"]["role"] == "technician"

        login = self.client.post(
            "/api/v1/admin/login",
            json={"username": payload["username"], "password": "tech-pass-123"},
        )
        assert login.status_code == 200, login.text
        assert login.json()["staff"]["role"] == "technician"
        assert login.json()["staff"]["technician_id"] == self.technician_id
        with self.SessionLocal() as db:
            activation_audit = db.scalar(select(AuditLog).where(
                AuditLog.action == "activate_technician",
                AuditLog.entity_type == "technician",
                AuditLog.entity_id == str(self.technician_id),
            ))
            assert activation_audit is not None

    def test_technician_can_read_own_profile_and_submit_leave(self):
        with self.SessionLocal() as db:
            staff = Staff(
                username="tech-direct",
                password_hash=hash_password("tech-pass"),
                name="小悦技师",
                role="technician",
                status="active",
                store_id=self.store_id,
                technician_id=self.technician_id,
            )
            db.add(staff)
            db.commit()
            staff_id = staff.id

        headers = {"Authorization": f"Bearer {create_staff_token(staff_id, 'technician')}"}
        me = self.client.get("/api/v1/technician/me", headers=headers)
        assert me.status_code == 200, me.text
        assert me.json()["technician"]["id"] == self.technician_id

        leave = self.client.post(
            "/api/v1/technician/leave-requests",
            headers=headers,
            json={
                "start_date": date.today().isoformat(),
                "end_date": (date.today() + timedelta(days=1)).isoformat(),
                "reason": "个人事务",
            },
        )
        assert leave.status_code == 200, leave.text
        assert leave.json()["status"] == "submitted"

    def test_admin_approves_leave_and_can_resign_technician(self):
        with self.SessionLocal() as db:
            staff = Staff(
                username="tech-lifecycle",
                password_hash=hash_password("tech-pass"),
                name="生命周期技师",
                role="technician",
                status="active",
                store_id=self.store_id,
                technician_id=self.technician_id,
            )
            db.add(staff)
            db.commit()
            staff_id = staff.id
        headers = {"Authorization": f"Bearer {create_staff_token(staff_id, 'technician')}"}
        leave = self.client.post(
            "/api/v1/technician/leave-requests",
            headers=headers,
            json={
                "start_date": date.today().isoformat(),
                "end_date": date.today().isoformat(),
                "reason": "休息",
            },
        )
        leave_id = leave.json()["id"]
        approved = self.client.post(
            f"/api/v1/admin/v2/technician-leave-requests/{leave_id}/approve",
            headers=self.admin_headers,
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"

        resigned = self.client.post(
            f"/api/v1/admin/v2/technicians/{self.technician_id}/resign",
            headers=self.admin_headers,
            json={"reason": "离职办理"},
        )
        assert resigned.status_code == 200, resigned.text
        assert resigned.json()["status"] == "resigned"
        denied = self.client.get("/api/v1/technician/me", headers=headers)
        assert denied.status_code == 401

    def test_technician_service_actions_only_update_diy_occupancy_and_are_idempotent_without_assignment(self):
        with self.SessionLocal() as db:
            staff = Staff(username="tech-actions", password_hash=hash_password("tech-pass"), name="小悦技师", role="technician", status="active", store_id=self.store_id, technician_id=self.technician_id)
            session = SelectionSession(id="tech-action-session", access_token_hash="hash", store_id=self.store_id, status="confirmed")
            room = Room(store_id=self.store_id, code="TECH-ACTION-ROOM", name="服务位", status="occupied")
            user = User(openid="tech-action-user")
            db.add_all([staff, session, room, user]); db.flush(); session.customer_id = user.id
            occupancy = PositionOccupancy(store_id=self.store_id, room_id=room.id, selection_session_id=session.id, active_room_id=room.id, active_session_id=session.id, status="waiting_service")
            db.add(occupancy); db.commit(); staff_id = staff.id; occupancy_id = occupancy.id
        headers = {"Authorization": f"Bearer {create_staff_token(staff_id, 'technician')}"}
        confirmed = self.client.post(f"/api/v1/technician/occupancies/{occupancy_id}/confirm", headers=headers, json={"idempotency_key": "confirm-1"})
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["status"] == "in_service"
        replay = self.client.post(f"/api/v1/technician/occupancies/{occupancy_id}/confirm", headers=headers, json={"idempotency_key": "confirm-1"})
        assert replay.status_code == 200
        finished = self.client.post(f"/api/v1/technician/occupancies/{occupancy_id}/finish", headers=headers, json={"idempotency_key": "finish-1"})
        assert finished.status_code == 200, finished.text
        assert finished.json()["status"] == "post_service_present"
        with self.SessionLocal() as db:
            audit = db.scalar(select(AuditLog).where(
                AuditLog.action == "technician_finish_service",
                AuditLog.entity_type == "position_occupancy",
                AuditLog.entity_id == str(occupancy_id),
                AuditLog.actor_id == str(staff_id),
            ))
            assert audit is not None
        profile = self.client.post(
            "/api/v1/admin/v2/customer-profile-records",
            headers={**headers, "Idempotency-Key": "tech-profile-action-001"},
            json={
                "user_id": user.id,
                "selection_session_id": "tech-action-session",
                "source": "both",
                "profile": {},
                "signals": ["偏好中等力度"],
                "note": "服务结束后记录",
            },
        )
        assert profile.status_code == 200, profile.text

    def test_technician_idempotency_key_cannot_be_reused_for_another_target_or_action(self):
        with self.SessionLocal() as db:
            staff = Staff(
                username="tech-idempotency-scope",
                password_hash=hash_password("tech-pass"),
                name="幂等技师",
                role="technician",
                status="active",
                store_id=self.store_id,
                technician_id=self.technician_id,
            )
            first_session = SelectionSession(
                id="tech-idempotency-first",
                access_token_hash="hash-first",
                store_id=self.store_id,
                status="submitted",
            )
            second_session = SelectionSession(
                id="tech-idempotency-second",
                access_token_hash="hash-second",
                store_id=self.store_id,
                status="submitted",
            )
            first_room = Room(
                store_id=self.store_id,
                code="IDEMPOTENCY-FIRST",
                name="幂等测试位 1",
                room_type="sofa",
                status="occupied",
            )
            second_room = Room(
                store_id=self.store_id,
                code="IDEMPOTENCY-SECOND",
                name="幂等测试位 2",
                room_type="sofa",
                status="occupied",
            )
            db.add_all([staff, first_session, second_session, first_room, second_room])
            db.flush()
            first = PositionOccupancy(
                store_id=self.store_id,
                room_id=first_room.id,
                active_room_id=first_room.id,
                selection_session_id=first_session.id,
                active_session_id=first_session.id,
                status="waiting_service",
            )
            second = PositionOccupancy(
                store_id=self.store_id,
                room_id=second_room.id,
                active_room_id=second_room.id,
                selection_session_id=second_session.id,
                active_session_id=second_session.id,
                status="waiting_service",
            )
            db.add_all([first, second])
            db.commit()
            staff_id = staff.id
            first_id = first.id
            second_id = second.id

        headers = {"Authorization": f"Bearer {create_staff_token(staff_id, 'technician')}"}
        first_confirm = self.client.post(
            f"/api/v1/technician/occupancies/{first_id}/confirm",
            headers=headers,
            json={"idempotency_key": "tech-scope-reuse-1"},
        )
        assert first_confirm.status_code == 200, first_confirm.text

        other_target = self.client.post(
            f"/api/v1/technician/occupancies/{second_id}/confirm",
            headers=headers,
            json={"idempotency_key": "tech-scope-reuse-1"},
        )
        assert other_target.status_code == 409, other_target.text
        assert other_target.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"

        other_action = self.client.post(
            f"/api/v1/technician/occupancies/{first_id}/finish",
            headers=headers,
            json={"idempotency_key": "tech-scope-reuse-1"},
        )
        assert other_action.status_code == 409, other_action.text
        assert other_action.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"

        with self.SessionLocal() as db:
            assert db.get(PositionOccupancy, first_id).status == "in_service"
            assert db.get(PositionOccupancy, second_id).status == "waiting_service"

    def test_technician_profile_authorization_uses_finished_occupancy_entity(self):
        """画像权限必须按本人完成的占用实体关联，而不能依赖脆弱的 JSON 会话字段。"""
        with self.SessionLocal() as db:
            staff = Staff(username="tech-profile-entity", password_hash=hash_password("tech-pass"), name="画像技师", role="technician", status="active", store_id=self.store_id, technician_id=self.technician_id)
            user = User(openid="tech-profile-entity-user")
            session = SelectionSession(id="tech-profile-entity-session", access_token_hash="hash", store_id=self.store_id, customer_id=None, status="completed")
            room = Room(store_id=self.store_id, code="PROFILE-ENTITY-ROOM", name="画像服务位", status="occupied")
            db.add_all([staff, user, session, room]); db.flush()
            session.customer_id = user.id
            occupancy = PositionOccupancy(store_id=self.store_id, room_id=room.id, selection_session_id=session.id, active_room_id=room.id, active_session_id=session.id, status="post_service_present", actual_service_end_at=datetime.now(timezone.utc))
            db.add(occupancy); db.flush()
            # 模拟历史审计 detail 缺失/不一致，但实体 ID 仍然准确。
            db.add(AuditLog(actor_type="staff", actor_id=str(staff.id), store_id=self.store_id, action="technician_finish_service", entity_type="position_occupancy", entity_id=str(occupancy.id), detail={"selection_session_id": "stale-session-id"}))
            db.commit()
            staff_id, user_id, session_id = staff.id, user.id, session.id
        headers = {"Authorization": f"Bearer {create_staff_token(staff_id, 'technician')}"}
        response = self.client.post(
            "/api/v1/admin/v2/customer-profile-records",
            headers={**headers, "Idempotency-Key": "tech-profile-entity-001"},
            json={"user_id": user_id, "selection_session_id": session_id, "source": "service_observation", "profile": {}, "signals": ["偏好中等力度"], "note": "实体关联验证"},
        )
        assert response.status_code == 200, response.text

    def test_technician_confirm_sets_expected_end_from_selected_project_duration(self):
        with self.SessionLocal() as db:
            staff = Staff(username="tech-duration", password_hash=hash_password("tech-pass"), name="时长技师", role="technician", status="active", store_id=self.store_id, technician_id=self.technician_id)
            project = Project(store_id=self.store_id, code="duration-project", category="bath", name="时长测试项目", duration_min=70, publication_status="published")
            db.add_all([staff, project])
            db.flush()
            db.add(PriceBook(project_id=project.id, price_type="store", amount_cents=1000))
            db.add(PriceBook(project_id=project.id, price_type="member", amount_cents=900))
            session = SelectionSession(id="tech-duration-session", access_token_hash="hash", store_id=self.store_id, status="submitted", items=[{"project_id": project.id, "quantity": 1, "item_type": "service"}])
            room = Room(store_id=self.store_id, code="DURATION-ROOM", name="时长测试位", room_type="sofa", status="occupied")
            db.add_all([session, room])
            db.flush()
            occupancy = PositionOccupancy(store_id=self.store_id, room_id=room.id, active_room_id=room.id, selection_session_id=session.id, active_session_id=session.id, status="waiting_service")
            db.add(occupancy)
            db.commit()
            staff_id = staff.id
            occupancy_id = occupancy.id

        headers = {"Authorization": f"Bearer {create_staff_token(staff_id, 'technician')}"}
        confirmed = self.client.post(
            f"/api/v1/technician/occupancies/{occupancy_id}/confirm",
            headers=headers,
            json={"idempotency_key": "confirm-duration-1"},
        )
        assert confirmed.status_code == 200, confirmed.text
        with self.SessionLocal() as db:
            saved = db.get(PositionOccupancy, occupancy_id)
            assert saved.status == "in_service"
            assert saved.actual_start_at is not None
            assert saved.expected_end_at is not None
            elapsed_minutes = (saved.expected_end_at - saved.actual_start_at).total_seconds() / 60
            assert elapsed_minutes == 70

    def test_technician_tasks_include_submitted_customer_order_by_service_position_without_assignment(self):
        with self.SessionLocal() as db:
            staff = Staff(username="tech-board", password_hash=hash_password("tech-pass"), name="看板技师", role="technician", status="active", store_id=self.store_id, technician_id=self.technician_id)
            session = SelectionSession(id="tech-board-session", access_token_hash="hash", store_id=self.store_id, status="submitted", customer_id=None, items=[{"name": "舒享精油 SPA", "quantity": 1}])
            room = Room(store_id=self.store_id, code="SOFA-01", name="大厅沙发 01", room_type="sofa", status="occupied")
            occupancy = PositionOccupancy(store_id=self.store_id, room_id=0, selection_session_id=session.id, status="waiting_service")
            db.add_all([staff, session, room])
            db.flush()
            occupancy.room_id = room.id
            occupancy.active_room_id = room.id
            occupancy.active_session_id = session.id
            db.add(occupancy)
            db.commit()
            staff_id = staff.id

        headers = {"Authorization": f"Bearer {create_staff_token(staff_id, 'technician')}"}
        response = self.client.get("/api/v1/technician/tasks", headers=headers)
        assert response.status_code == 200, response.text
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["room_name"] == "大厅沙发 01"
        assert items[0]["room_type"] == "sofa"
        assert "assignment_status" not in items[0]
        assert items[0]["completed_by_me"] is False
        assert items[0]["selection_status"] == "submitted"
        assert items[0]["items"][0]["name"] == "舒享精油 SPA"

    def test_technician_tasks_show_one_room_card_instead_of_its_beds(self):
        with self.SessionLocal() as db:
            staff = Staff(username="tech-empty-board", password_hash=hash_password("tech-pass"), name="空位看板技师", role="technician", status="active", store_id=self.store_id, technician_id=self.technician_id)
            sofa = Room(store_id=self.store_id, code="SOFA-EMPTY", name="大厅沙发 02", room_type="sofa", status="available", is_service_position=True, is_space_container=False, operational_status="active")
            room = Room(store_id=self.store_id, code="ROOM-CONTAINER", name="1号房间", room_type="room", status="available", is_service_position=False, is_space_container=True, operational_status="active")
            bed = Room(store_id=self.store_id, code="BED-EMPTY", name="1号房间 A 床", room_type="bed", status="available", is_service_position=True, is_space_container=False, operational_status="active", parent_room_id=None)
            db.add_all([staff, sofa, room, bed])
            db.flush()
            bed.parent_room_id = room.id
            db.commit()
            staff_id = staff.id

        headers = {"Authorization": f"Bearer {create_staff_token(staff_id, 'technician')}"}
        response = self.client.get("/api/v1/technician/tasks", headers=headers)
        assert response.status_code == 200, response.text
        items = response.json()["items"]
        assert {item["room_name"] for item in items} == {"大厅沙发 02", "1号房间"}
        assert next(item for item in items if item["room_name"] == "1号房间")["room_type"] == "room"
        assert all(item["occupancy_id"] is None for item in items)
        assert all(item["occupancy_status"] == "available" for item in items)
        assert all(item["items"] == [] for item in items)

    def test_technician_tasks_do_not_expose_orphan_bed_as_standalone_position(self):
        with self.SessionLocal() as db:
            staff = Staff(
                username="tech-orphan-bed",
                password_hash=hash_password("tech-pass"),
                name="孤立床位看板技师",
                role="technician",
                status="active",
                store_id=self.store_id,
                technician_id=self.technician_id,
            )
            sofa = Room(
                store_id=self.store_id,
                code="SOFA-ORPHAN-BED",
                name="大厅沙发 03",
                room_type="sofa",
                status="available",
                is_service_position=True,
                is_space_container=False,
                operational_status="active",
            )
            orphan_bed = Room(
                store_id=self.store_id,
                code="BED-ORPHAN",
                name="未归属房间 A 床",
                room_type="bed",
                status="available",
                is_service_position=True,
                is_space_container=False,
                operational_status="active",
                parent_room_id=None,
            )
            db.add_all([staff, sofa, orphan_bed])
            db.commit()
            staff_id = staff.id

        headers = {"Authorization": f"Bearer {create_staff_token(staff_id, 'technician')}"}
        response = self.client.get("/api/v1/technician/tasks", headers=headers)

        assert response.status_code == 200, response.text
        assert [item["room_name"] for item in response.json()["items"]] == ["大厅沙发 03"]

    def test_technician_tasks_map_a_bed_order_to_its_parent_room(self):
        with self.SessionLocal() as db:
            staff = Staff(username="tech-room-board", password_hash=hash_password("tech-pass"), name="房间看板技师", role="technician", status="active", store_id=self.store_id, technician_id=self.technician_id)
            room = Room(store_id=self.store_id, code="ROOM-ORDER", name="2号房间", room_type="room", status="occupied", is_service_position=False, is_space_container=True, operational_status="active")
            bed = Room(store_id=self.store_id, code="BED-ORDER", name="2号房间 A 床", room_type="bed", status="occupied", is_service_position=True, is_space_container=False, operational_status="active")
            session = SelectionSession(id="tech-room-session", access_token_hash="hash", store_id=self.store_id, status="submitted", items=[{"name": "荷小推", "quantity": 1}])
            db.add_all([staff, room, bed, session])
            db.flush()
            bed.parent_room_id = room.id
            occupancy = PositionOccupancy(store_id=self.store_id, room_id=bed.id, selection_session_id=session.id, active_room_id=bed.id, active_session_id=session.id, status="waiting_service")
            db.add(occupancy)
            db.commit()
            staff_id = staff.id
            occupancy_id = occupancy.id

        headers = {"Authorization": f"Bearer {create_staff_token(staff_id, 'technician')}"}
        response = self.client.get("/api/v1/technician/tasks", headers=headers)
        assert response.status_code == 200, response.text
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["room_name"] == "2号房间"
        assert items[0]["room_type"] == "room"
        assert items[0]["occupancy_id"] == occupancy_id
        assert items[0]["items"][0]["name"] == "荷小推"
