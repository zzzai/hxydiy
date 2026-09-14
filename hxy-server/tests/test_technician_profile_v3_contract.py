import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import AuditLog, CustomerProfileCurrent, CustomerProfileRecord, Order, PositionOccupancy, SelectionSession, Staff, Store, User
from app.models.operations import Room, Technician


class TestTechnicianServiceContinuityContract:
    def setup_method(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        with self.SessionLocal() as db:
            store = Store(store_code='continuity-store', name='服务连续性测试店', address='测试地址')
            customer = User(openid='continuity-customer', nickname='顾客')
            db.add_all([store, customer])
            db.flush()
            technician = Technician(store_id=store.id, code='CONTINUITY-TECH', name='测试技师', status='available')
            staff = Staff(username='continuity-tech', password_hash=hash_password('tech-pass'), name='测试技师', role='technician', status='active', store_id=store.id)
            room = Room(store_id=store.id, code='CONTINUITY-SOFA', name='测试沙发', room_type='sofa', status='occupied')
            session = SelectionSession(id='continuity-session', store_id=store.id, customer_id=customer.id, access_token_hash='continuity-token', status='completed', items=[{'name': '草本泡脚'}])
            db.add_all([technician, staff, room, session, Order(order_no='CONTINUITY-ORDER', order_type='service', user_id=customer.id, store_id=store.id, items=[], status='completed', pay_status='paid')])
            db.flush()
            staff.technician_id = technician.id
            occupancy = PositionOccupancy(store_id=store.id, room_id=room.id, selection_session_id=session.id, active_room_id=room.id, active_session_id=session.id, status='post_service_present', actual_service_end_at=datetime.now(timezone.utc))
            db.add(occupancy)
            db.flush()
            db.add(AuditLog(actor_type='staff', actor_id=str(staff.id), store_id=store.id, action='technician_finish_service', entity_type='position_occupancy', entity_id=str(occupancy.id), detail={'selection_session_id': session.id}))
            db.commit()
            self.store_id, self.user_id, self.staff_id, self.technician_id, self.room_id, self.session_id = store.id, customer.id, staff.id, technician.id, room.id, session.id
        app.dependency_overrides[get_db] = self._override_get_db
        self.client = TestClient(app)
        self.technician_headers = {'Authorization': f'Bearer {create_staff_token(self.staff_id, "technician")}', 'Idempotency-Key': 'continuity-001'}

    def teardown_method(self):
        app.dependency_overrides.clear()
        self.client.close()
        self.engine.dispose()

    def _override_get_db(self):
        with self.SessionLocal() as db:
            yield db

    def v5_payload(self, *, confirmed=True, observed=None, reported=None, next_visit=None):
        return {
            'user_id': self.user_id, 'selection_session_id': self.session_id,
            'schema_version': 5, 'taxonomy_version': 'service_reference_v4', 'customer_confirmed': confirmed,
            'profile': {
                'schema_version': 5, 'taxonomy_version': 'service_reference_v4',
                'customer_reported': reported or {}, 'technician_observed': observed or {}, 'next_visit': next_visit or {},
            }, 'signals': [], 'note': '',
        }

    def seed_legacy_v3(self):
        profile = {
            'schema_version': 3, 'taxonomy_version': 'service_reference_v2',
            'customer_reported': {
                'force_preference': 'gentle', 'personal_context': {'age_band': '25_34'},
                'work_lifestyle': {'occupation_contexts': ['desk_work']},
                'service_related_context': {'contexts': ['medication_mentioned'], 'quote': '顾客自述正在用药'},
            }, 'technician_observed': {'session_response': {'relaxation': 'gradual'}}, 'next_visit': {'plan': 'confirm_on_arrival'},
        }
        with self.SessionLocal() as db:
            record = CustomerProfileRecord(store_id=self.store_id, user_id=self.user_id, selection_session_id='legacy-session', technician_id=self.technician_id, created_by_staff_id=self.staff_id, source='both', schema_version=3, taxonomy_version='service_reference_v2', customer_confirmed=True, confirmed_at=datetime.now(timezone.utc), idempotency_key='legacy-seed', profile=profile, signals=[], note='')
            db.add(record)
            db.commit()
            return record.id

    def next_service_occupancy(self, session_id='next-continuity-session'):
        with self.SessionLocal() as db:
            current = db.query(PositionOccupancy).first()
            current.active_room_id = None
            current.active_session_id = None
            session = SelectionSession(id=session_id, store_id=self.store_id, customer_id=self.user_id, access_token_hash=session_id, status='submitted', items=[])
            db.add(session)
            db.flush()
            occupancy = PositionOccupancy(store_id=self.store_id, room_id=self.room_id, selection_session_id=session.id, active_room_id=self.room_id, active_session_id=session.id, status='waiting_service')
            db.add(occupancy)
            db.commit()
            return occupancy.id

    def test_v5_records_safe_preference_adjustment_feedback_and_replay(self):
        payload = self.v5_payload(confirmed=True, reported={'communication_preference': 'quiet', 'force_preference': 'gentle'}, observed={'service_adjustments': ['pressure_lighter', 'pace_slower'], 'service_feedback': 'better_after_adjustment'}, next_visit={'plan': 'confirm_on_arrival'})
        saved = self.client.post('/api/v1/admin/v2/customer-profile-records', json=payload, headers=self.technician_headers)
        assert saved.status_code == 200, saved.text
        replay = self.client.post('/api/v1/admin/v2/customer-profile-records', json=payload, headers=self.technician_headers)
        assert replay.status_code == 200
        assert replay.json()['id'] == saved.json()['id']
        with self.SessionLocal() as db:
            record = db.get(CustomerProfileRecord, saved.json()['id'])
            assert record.profile['technician_observed']['service_adjustments'] == ['pressure_lighter', 'pace_slower']
            assert db.query(CustomerProfileCurrent).filter_by(customer_id=self.user_id).count() == 0

    @pytest.mark.parametrize('schema_version,taxonomy_version,profile', [
        (2, 'service_reference_v1', {'schema_version': 2, 'taxonomy_version': 'service_reference_v1', 'customer_reported': {'force_preference': 'gentle'}, 'technician_observed': {}, 'next_visit': {}}),
        (3, 'service_reference_v2', {'schema_version': 3, 'taxonomy_version': 'service_reference_v2', 'customer_reported': {'personal_context': {'age_band': '25_34'}}, 'technician_observed': {}, 'next_visit': {}}),
        (4, 'service_reference_v3', {'schema_version': 4, 'taxonomy_version': 'service_reference_v3', 'customer_reported': {'body_service_notes': [{'area': 'knee', 'context': 'old_injury', 'reconfirm_next_visit': True}]}, 'technician_observed': {}, 'next_visit': {}}),
    ])
    def test_v1_to_v4_service_reference_writes_are_rejected(self, schema_version, taxonomy_version, profile):
        payload = {'user_id': self.user_id, 'selection_session_id': self.session_id, 'schema_version': schema_version, 'taxonomy_version': taxonomy_version, 'customer_confirmed': True, 'profile': profile, 'signals': [], 'note': ''}
        response = self.client.post('/api/v1/admin/v2/customer-profile-records', json=payload, headers={**self.technician_headers, 'Idempotency-Key': f'legacy-{schema_version}'})
        assert response.status_code == 422, response.text

    def test_v5_rejects_legacy_fields_and_duplicate_adjustments(self):
        for reported, observed, key in [
            ({'personal_context': {'age_band': '25_34'}}, {}, 'v5-legacy-field'),
            ({}, {'service_adjustments': ['pressure_lighter', 'pressure_lighter']}, 'v5-duplicate-adjustment'),
        ]:
            response = self.client.post('/api/v1/admin/v2/customer-profile-records', json=self.v5_payload(reported=reported, observed=observed), headers={**self.technician_headers, 'Idempotency-Key': key})
            assert response.status_code == 422, response.text

    def test_historical_record_is_redacted_for_manager_and_safe_for_next_service(self):
        self.seed_legacy_v3()
        with self.SessionLocal() as db:
            manager = Staff(username='continuity-manager', password_hash=hash_password('pass'), name='店长', role='manager', status='active', store_id=self.store_id)
            db.add(manager)
            db.commit()
            manager_id = manager.id
        response = self.client.get(f'/api/v1/admin/v2/users/{self.user_id}/customer-profile-records', headers={'Authorization': f'Bearer {create_staff_token(manager_id, "manager")}'} )
        assert response.status_code == 200, response.text
        serialized = json.dumps(response.json(), ensure_ascii=False)
        for forbidden in ('age_band', 'occupation_contexts', 'medication_mentioned', '顾客自述正在用药'):
            assert forbidden not in serialized
        occupancy_id = self.next_service_occupancy()
        reference = self.client.get(f'/api/v1/technician/occupancies/{occupancy_id}/service-reference', headers=self.technician_headers)
        assert reference.status_code == 200, reference.text
        record = reference.json()['record']
        assert record['force_preference'] == '轻柔'
        assert 'occupation_contexts' not in record
        assert '顾客自述正在用药' not in json.dumps(record, ensure_ascii=False)

    def test_v5_body_detail_is_reduced_to_reconfirmation(self):
        notes = [{'region': 'shoulder', 'side': 'right', 'context': 'long_term_discomfort_mentioned', 'current_state': 'occasional_discomfort', 'session_handling': 'lighter', 'reconfirm_next_visit': True}]
        saved = self.client.post('/api/v1/admin/v2/customer-profile-records', json=self.v5_payload(reported={'body_service_notes': notes}), headers=self.technician_headers)
        assert saved.status_code == 200, saved.text
        with self.SessionLocal() as db:
            manager = Staff(username='body-manager', password_hash=hash_password('pass'), name='店长', role='manager', status='active', store_id=self.store_id)
            db.add(manager)
            db.commit()
            manager_id = manager.id
        response = self.client.get(f'/api/v1/admin/v2/users/{self.user_id}/customer-profile-records', headers={'Authorization': f'Bearer {create_staff_token(manager_id, "manager")}'} )
        item = response.json()['items'][0]
        assert item['body_reconfirm_required'] is True
        assert 'shoulder' not in json.dumps(item, ensure_ascii=False)
        occupancy_id = self.next_service_occupancy('next-body-session')
        reference = self.client.get(f'/api/v1/technician/occupancies/{occupancy_id}/service-reference', headers=self.technician_headers).json()['record']
        assert reference['body_reconfirm_required'] is True
        assert 'shoulder' not in json.dumps(reference, ensure_ascii=False)

    def test_taxonomy_exposes_only_safe_v5_service_codes(self):
        response = self.client.get('/api/v1/technician/service-reference-taxonomy', headers=self.technician_headers)
        assert response.status_code == 200, response.text
        groups = response.json()['groups']
        assert groups['service_adjustments']['pressure_lighter'] == '减轻力度'
        assert groups['body_service_notes']['regions']['knee'] == '膝部'
        for forbidden in ('occupation_contexts', 'personal_context', 'work_lifestyle', 'communication_consumption'):
            assert forbidden not in groups

    def test_manager_current_profile_hides_historical_personal_dimensions(self):
        legacy_id = self.seed_legacy_v3()
        now = datetime.now(timezone.utc)
        with self.SessionLocal() as db:
            db.add_all([
                CustomerProfileCurrent(customer_id=self.user_id, store_id=self.store_id, profile_code='age_band', profile_value_key='25_34', profile_value_json={'value': '25_34'}, source_record_id=legacy_id, first_confirmed_at=now, last_confirmed_at=now, confirmation_count=1, valid_until=now + timedelta(days=1), taxonomy_version='service_reference_v2', status='active'),
                CustomerProfileCurrent(customer_id=self.user_id, store_id=self.store_id, profile_code='force_preference', profile_value_key='gentle', profile_value_json={'value': 'gentle'}, source_record_id=legacy_id, first_confirmed_at=now, last_confirmed_at=now, confirmation_count=1, valid_until=now + timedelta(days=1), taxonomy_version='service_reference_v2', status='active'),
            ])
            manager = Staff(username='current-manager', password_hash=hash_password('pass'), name='店长', role='manager', status='active', store_id=self.store_id)
            db.add(manager)
            db.commit()
            manager_id = manager.id
        denied = self.client.get(f'/api/v1/admin/v2/users/{self.user_id}/customer-profile-current', headers=self.technician_headers)
        assert denied.status_code == 403
        response = self.client.get(f'/api/v1/admin/v2/users/{self.user_id}/customer-profile-current', headers={'Authorization': f'Bearer {create_staff_token(manager_id, "manager")}'} )
        assert response.status_code == 200, response.text
        assert [item['profile_code'] for item in response.json()['items']] == ['force_preference']
