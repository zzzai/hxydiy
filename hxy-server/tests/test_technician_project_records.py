from copy import deepcopy

from sqlalchemy import select

from app.models import CustomerProfileRecord, SelectionSession, PositionOccupancy, Staff
from app.models.operations import Technician
from app.api.admin import create_staff_token, hash_password
from test_technician_profile_quick_note_contract import TestTechnicianProfileQuickNoteContract as Fixture


class TestProjectRecords:
    setup_method = Fixture.setup_method
    teardown_method = Fixture.teardown_method
    _override_get_db = Fixture._override_get_db

    def payload(self):
        with self.SessionLocal() as db:
            db.get(SelectionSession, self.session_id).items = [{"name": "招牌草本泡"}]
            db.commit()
        return {
            "user_id": self.own_user_id, "selection_session_id": self.session_id,
            "schema_version": 6, "taxonomy_version": "service_record_v1",
            "customer_confirmed": False,
            "profile": {"schema_version": 6, "taxonomy_version": "service_record_v1",
                        "template": "herbal_signature_v1",
                        "massage": [{"region": "shoulder", "side": "left", "request": "lighter"}],
                        "service_note": "下次询问预约时间"},
        }

    def post(self, payload, key="project-record-001"):
        return self.client.post('/api/v1/admin/v2/customer-profile-records', json=payload,
                                headers={**self.headers, 'Idempotency-Key': key})

    def test_request_is_saved_without_invented_action_or_feedback(self):
        payload = self.payload()
        response = self.post(payload)
        assert response.status_code == 200, response.text
        assert response.json()['profile']['massage'] == [{'region': 'shoulder', 'side': 'left', 'request': 'lighter'}]
        assert self.post(payload).json()['id'] == response.json()['id']
        changed = deepcopy(payload)
        changed['profile']['massage'][0]['request'] = 'stronger'
        assert self.post(changed).status_code == 409

    def test_rejects_unknown_codes_and_no_new_mixed_with_content(self):
        payload = self.payload()
        for patch in ({'recording_outcome': 'no_additional_notes'}, {'water': {'request': 'unknown'}}):
            bad = deepcopy(payload)
            bad['profile'].update(patch)
            assert self.post(bad).status_code == 422

    def test_only_author_can_correct_and_original_is_retained(self):
        payload = self.payload()
        first = self.post(payload)
        assert first.status_code == 200, first.text
        payload['correction_of_id'] = first.json()['id']
        payload['correction_reason'] = '更正本次记录'
        payload['profile']['massage'][0]['request'] = 'stronger'
        revised = self.post(payload, 'project-record-002')
        assert revised.status_code == 200, revised.text
        assert self.post(payload, 'project-record-003').status_code == 409
        with self.SessionLocal() as db:
            original = db.get(CustomerProfileRecord, first.json()['id'])
            assert original.profile['massage'][0]['request'] == 'lighter'
            original.created_by_staff_id = 999
            db.commit()
        assert self.post(payload, 'project-record-004').status_code in (403, 404)

    def test_template_requires_matching_service(self):
        payload = self.payload()
        with self.SessionLocal() as db:
            db.get(SelectionSession, self.session_id).items = [{'name': '采耳'}]
            db.commit()
        assert self.post(payload).status_code == 422

    def test_version_validation_and_service_ownership_cannot_be_bypassed(self):
        payload = self.payload()
        invalid = []
        for patch in ({'massage': [{'region':'shoulder','side':'center','request':'lighter'}]},
                      {'massage': [{'region':'shoulder','side':'left','request':'lighter'}] * 4},
                      {'service_note':'诊断为肩周炎'}, {'unknown_field':'secret'}):
            bad = deepcopy(payload);bad['profile'].update(patch);invalid.append(bad)
        for version in (1, 5):
            bad=deepcopy(payload);bad['schema_version']=version;invalid.append(bad)
        for bad in invalid:
            assert self.post(bad).status_code == 422
        other=deepcopy(payload);other['user_id']=self.other_user_id
        assert self.post(other).status_code == 404
        with self.SessionLocal() as db:
            db.get(Staff,self.staff_id).role='manager'
            db.commit()
        assert self.post(payload).status_code == 403

    def test_management_view_does_not_receive_private_text(self):
        from app.api.admin_v2 import _management_profile_record_view
        response = self.post(self.payload())
        assert response.status_code == 200, response.text
        with self.SessionLocal() as db:
            record = db.get(CustomerProfileRecord, response.json()['id'])
            view = _management_profile_record_view(record, db)
            assert '下次询问预约时间' not in str(view)
            assert 'massage' not in str(view)

    def test_own_versions_are_private_and_summary_has_no_free_text(self):
        from app.api.technician import _history_profile_summary
        response = self.post(self.payload())
        assert response.status_code == 200, response.text
        record_id = response.json()['id']
        history = self.client.get(f'/api/v1/technician/service-records/{record_id}/versions', headers=self.headers)
        assert history.status_code == 200, history.text
        assert history.json()['items'][0]['profile']['service_note'] == '下次询问预约时间'
        with self.SessionLocal() as db:
            record = db.get(CustomerProfileRecord, record_id)
            summary = _history_profile_summary(record)
            assert summary['service_lines'] == ['左侧肩部：顾客要求轻一点']
            assert '下次询问预约时间' not in str(summary)
            record.created_by_staff_id = 999
            db.commit()
        assert self.client.get(f'/api/v1/technician/service-records/{record_id}/versions', headers=self.headers).status_code == 404

    def test_other_technician_reads_only_confirmed_safe_reference_for_active_customer(self):
        payload = self.payload()
        payload['customer_confirmed'] = True
        assert self.post(payload).status_code == 200
        with self.SessionLocal() as db:
            old = db.scalar(select(PositionOccupancy).where(PositionOccupancy.selection_session_id == self.session_id))
            old.active_room_id = None
            old.active_session_id = None
            db.flush()
            session = SelectionSession(id='next-project-visit',store_id=old.store_id,customer_id=self.own_user_id,access_token_hash='test-next',status='submitted',items=[])
            technician = Technician(store_id=old.store_id,code='NEXT-TECH',name='下次服务技师',status='available')
            db.add_all([session,technician]);db.flush()
            staff = Staff(username='next-project-tech',password_hash=hash_password('local-test-only'),name='下次服务技师',role='technician',status='active',store_id=old.store_id,technician_id=technician.id)
            active = PositionOccupancy(store_id=old.store_id,room_id=old.room_id,active_room_id=old.room_id,selection_session_id=session.id,active_session_id=session.id,status='waiting_service')
            db.add_all([staff,active]);db.commit()
            auth = {'Authorization':f'Bearer {create_staff_token(staff.id,"technician")}'}
            occupancy_id = active.id
        response = self.client.get(f'/api/v1/technician/occupancies/{occupancy_id}/service-reference',headers=auth)
        assert response.status_code == 200, response.text
        assert response.json()['record']['service_lines'] == ['左侧肩部：顾客要求轻一点']
        assert '下次询问预约时间' not in response.text
        with self.SessionLocal() as db:
            db.get(PositionOccupancy,occupancy_id).active_room_id = None
            db.commit()
        assert self.client.get(f'/api/v1/technician/occupancies/{occupancy_id}/service-reference',headers=auth).status_code == 409

    def test_service_history_includes_real_record_link_without_private_text(self):
        response = self.post(self.payload())
        assert response.status_code == 200
        with self.SessionLocal() as db:
            occupancy = db.scalar(select(PositionOccupancy).where(PositionOccupancy.selection_session_id == self.session_id))
            occupancy.serviced_by_technician_id = self.technician_id
            db.commit()
        history = self.client.get('/api/v1/technician/service-history',headers=self.headers)
        assert history.status_code == 200, history.text
        item=history.json()['items'][0]
        assert item['own_record_id'] == response.json()['id']
        assert item['record_completed'] is True
        assert item['own_record_summary']['service_lines'] == ['左侧肩部：顾客要求轻一点']
        assert '下次询问预约时间' not in history.text
