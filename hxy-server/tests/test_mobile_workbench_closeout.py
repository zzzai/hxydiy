import unittest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token
from app.db.session import Base, get_db
from app.main import app
from app.models import (
    AuditLog, CustomerProfileRecord, OperationalException, PositionOccupancy,
    Room, SelectionSession, Staff, Store, Technician, User,
)


class MobileWorkbenchCloseoutTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        with self.Session() as db:
            self.store = Store(store_code='closeout-1', name='Test store', address='Test')
            self.other = Store(store_code='closeout-2', name='Other store', address='Test')
            db.add_all([self.store, self.other])
            db.flush()
            self.tech = Technician(store_id=self.store.id, code='closeout-tech', name='Test technician')
            self.user = User(openid='closeout-synthetic-user')
            self.room = Room(store_id=self.store.id, code='closeout-room', name='Test sofa', room_type='sofa')
            db.add_all([self.tech, self.user, self.room])
            db.flush()
            self.manager = Staff(store_id=self.store.id, username='closeout-manager', name='Test manager', role='admin', status='active', password_hash='unused')
            self.worker = Staff(store_id=self.store.id, username='closeout-worker', name='Test worker', role='technician', technician_id=self.tech.id, status='active', password_hash='unused')
            db.add_all([self.manager, self.worker])
            db.commit()
        def override_db():
            with self.Session() as db:
                yield db
        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)
        self.headers = {'Authorization': 'Bearer ' + create_staff_token(self.manager.id, 'admin')}
        self.worker_headers = {'Authorization': 'Bearer ' + create_staff_token(self.worker.id, 'technician')}

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def service(self, key, *, days=0, ended=True, attested=True, store_id=None):
        with self.Session() as db:
            session = SelectionSession(id=key, access_token_hash='synthetic', store_id=store_id or self.store.id, customer_id=self.user.id, status='confirmed', source='personal_qr', items=[{'name': 'Test service'}], diy_preferences={})
            db.add(session)
            db.flush()
            occupancy = PositionOccupancy(store_id=store_id or self.store.id, room_id=self.room.id, selection_session_id=key, serviced_by_technician_id=self.tech.id, status='released' if ended else 'in_service', actual_service_end_at=datetime.now(timezone.utc) - timedelta(days=days) if ended else None)
            db.add(occupancy)
            db.flush()
            if attested:
                db.add(AuditLog(store_id=store_id or self.store.id, actor_type='staff', actor_id=str(self.worker.id), action='technician_finish_service', entity_type='position_occupancy', entity_id=str(occupancy.id), detail={}))
            db.commit()
            return occupancy.id

    def record(self, key, *, confirmed=False, version=7, taxonomy='service_handoff_v1', author=None, correction_of=None):
        with self.Session() as db:
            record = CustomerProfileRecord(store_id=self.store.id, user_id=self.user.id, selection_session_id=key, technician_id=self.tech.id, created_by_staff_id=author or self.worker.id, schema_version=version, taxonomy_version=taxonomy, customer_confirmed=confirmed, profile={'recording_outcome': 'no_additional_notes', 'private_marker': 'PRIVATE-CONTENT'}, correction_of_id=correction_of)
            db.add(record)
            db.commit()
            return record.id

    def exceptions(self):
        with self.Session() as db:
            rows = [OperationalException(store_id=self.store.id, exception_type='missing_order', severity='warning', status=status, dedupe_key='synthetic-' + status, title='Test issue', detail={}, entity_type='selection_session', entity_id='synthetic', due_at=datetime.now(timezone.utc) - timedelta(hours=1)) for status in ['open', 'acknowledged', 'resolved']]
            db.add_all(rows)
            db.add(OperationalException(store_id=self.other.id, exception_type='missing_order', status='open', dedupe_key='other', title='Other store', detail={}, entity_type='selection_session', entity_id='other'))
            db.commit()
            return [row.id for row in rows]

    def test_unresolved_includes_acknowledged_without_other_store_or_resolved(self):
        opened, acknowledged, resolved = self.exceptions()
        response = self.client.get('/api/v1/admin/exceptions?status=unresolved', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row['id'] for row in response.json()['items']}, {opened, acknowledged})
        workbench = self.client.get('/api/v1/admin/v2/manager/workbench', headers=self.headers).json()
        self.assertEqual(workbench['summary']['open_exceptions'], 2)
        self.assertEqual(workbench['summary']['overdue_exceptions'], 2)
        self.assertEqual(workbench['summary']['attention'], 2)

    def test_acknowledge_retry_keeps_timestamp_and_single_audit(self):
        opened, _, resolved = self.exceptions()
        first = self.client.post(f'/api/v1/admin/exceptions/{opened}/acknowledge', headers=self.headers)
        second = self.client.post(f'/api/v1/admin/exceptions/{opened}/acknowledge', headers=self.headers)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()['acknowledged_at'], second.json()['acknowledged_at'])
        with self.Session() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == 'acknowledge_operational_exception')), 1)
        self.assertEqual(self.client.post(f'/api/v1/admin/exceptions/{resolved}/acknowledge', headers=self.headers).status_code, 409)

    def test_saved_unconfirmed_record_is_complete_and_manager_never_sees_content(self):
        self.service('pending')
        self.service('saved')
        self.record('saved', confirmed=False)
        self.service('in-progress', ended=False)
        self.service('old', days=31)
        self.service('unattributed', attested=False)
        self.service('other-store', store_id=self.other.id)
        with self.Session() as db:
            before = {table.name: db.scalar(select(func.count()).select_from(table)) for table in Base.metadata.tables.values()}
        response = self.client.get('/api/v1/admin/v2/manager/workbench', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        follow_up = response.json().get('record_follow_up', {})
        self.assertEqual(follow_up.get('pending_count'), 1)
        self.assertEqual(follow_up.get('window_days'), 30)
        self.assertEqual(follow_up.get('technicians'), [{'technician_id': self.tech.id, 'name': self.tech.name, 'count': 1}])
        self.assertNotIn('PRIVATE-CONTENT', response.text)
        self.assertNotIn('customer_id', response.text)
        self.assertNotIn('profile', response.text)
        self.record('pending')
        self.assertEqual(self.client.get('/api/v1/admin/v2/manager/workbench', headers=self.headers).json()['record_follow_up']['pending_count'], 0)
        with self.Session() as db:
            after = {table.name: db.scalar(select(func.count()).select_from(table)) for table in Base.metadata.tables.values()}
        expected = dict(before)
        expected['customer_profile_records'] += 1
        self.assertEqual(after, expected)

    def test_unsupported_or_other_author_record_does_not_clear_pending(self):
        self.service('unsupported')
        self.record('unsupported', version=1, taxonomy=None)
        self.service('wrong-author')
        self.record('wrong-author', author=self.manager.id)
        response = self.client.get('/api/v1/admin/v2/manager/workbench', headers=self.headers)
        self.assertEqual(response.json().get('record_follow_up', {}).get('pending_count'), 2)

    def test_history_pending_record_filter_is_not_customer_confirmation(self):
        pending = self.service('history-pending')
        self.service('history-saved')
        self.record('history-saved', confirmed=False)
        response = self.client.get('/api/v1/technician/service-history?record_status=pending', headers=self.worker_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['total'], 1)
        item = response.json()['items'][0]
        self.assertEqual(item['occupancy_id'], pending)
        self.assertEqual(item.get('record_task', {}).get('selection_session_id'), 'history-pending')
        self.assertEqual(item['record_task']['user_id'], self.user.id)
        invalid = self.client.get('/api/v1/technician/service-history?record_status=unknown', headers=self.worker_headers)
        self.assertEqual(invalid.status_code, 422)

    def test_history_cannot_offer_recording_without_finish_audit(self):
        self.service('history-unattributed', attested=False)
        response = self.client.get('/api/v1/technician/service-history', headers=self.worker_headers)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['items'][0].get('record_task'))

    def test_record_save_and_idempotent_retry_clear_only_owned_reminder(self):
        self.service('save-from-history')
        self.service('keep-pending')
        payload = {
            'user_id': self.user.id, 'selection_session_id': 'save-from-history',
            'schema_version': 7, 'taxonomy_version': 'service_handoff_v1',
            'customer_confirmed': False, 'signals': [], 'note': '',
            'profile': {'schema_version': 7, 'taxonomy_version': 'service_handoff_v1', 'recording_outcome': 'no_additional_notes'},
        }
        headers = {**self.worker_headers, 'Idempotency-Key': 'synthetic-closeout-save'}
        first = self.client.post('/api/v1/admin/v2/customer-profile-records', json=payload, headers=headers)
        self.assertEqual(first.status_code, 200, first.text)
        repeated = self.client.post('/api/v1/admin/v2/customer-profile-records', json=payload, headers=headers)
        self.assertEqual(repeated.json()['id'], first.json()['id'])
        history = self.client.get('/api/v1/technician/service-history?record_status=pending', headers=self.worker_headers).json()
        self.assertEqual(history['total'], 1)
        self.assertEqual(history['items'][0]['record_task']['selection_session_id'], 'keep-pending')
        self.assertEqual(self.client.get('/api/v1/admin/v2/manager/workbench', headers=self.headers).json()['record_follow_up']['pending_count'], 1)
        with self.Session() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CustomerProfileRecord)), 1)

    def test_anonymous_and_replaced_occupancies_are_not_actionable_record_tasks(self):
        self.service('anonymous')
        old_id = self.service('replaced')
        with self.Session() as db:
            db.get(SelectionSession, 'anonymous').customer_id = None
            db.add(PositionOccupancy(store_id=self.store.id, room_id=self.room.id, selection_session_id='replaced', status='waiting_service'))
            db.commit()
        history = self.client.get('/api/v1/technician/service-history?record_status=pending', headers=self.worker_headers).json()
        self.assertEqual(history['total'], 0)
        self.assertEqual(history['items'], [])
        self.assertEqual(self.client.get('/api/v1/admin/v2/manager/workbench', headers=self.headers).json()['record_follow_up']['pending_count'], 0)
        history = self.client.get('/api/v1/technician/service-history', headers=self.worker_headers).json()
        self.assertIsNone(next(item for item in history['items'] if item['occupancy_id'] == old_id)['record_task'])

    def test_cross_store_acknowledge_is_denied_without_audit(self):
        self.exceptions()
        with self.Session() as db:
            foreign_id = db.scalar(select(OperationalException.id).where(OperationalException.store_id == self.other.id))
        response = self.client.post(f'/api/v1/admin/exceptions/{foreign_id}/acknowledge', headers=self.headers)
        self.assertEqual(response.status_code, 404)
        with self.Session() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(AuditLog)), 0)

    def test_only_currently_writable_technicians_receive_record_tasks(self):
        self.service('role-check')
        for role, status in [('staff', 'available'), ('manager', 'available'), ('technician', 'off')]:
            with self.subTest(role=role, status=status):
                with self.Session() as db:
                    db.get(Staff, self.worker.id).role = role
                    db.get(Technician, self.tech.id).status = status
                    db.commit()
                headers = {'Authorization': 'Bearer ' + create_staff_token(self.worker.id, role)}
                summary = self.client.get('/api/v1/admin/v2/manager/workbench', headers=self.headers).json()
                self.assertEqual(summary['record_follow_up']['pending_count'], 0)
                history = self.client.get('/api/v1/technician/service-history', headers=headers)
                if role == 'manager':
                    self.assertEqual(history.status_code, 200)
                    self.assertIsNone(history.json()['items'][0]['record_task'])
                    pending = self.client.get('/api/v1/technician/service-history?record_status=pending', headers=headers)
                    self.assertEqual(pending.json()['total'], 0)
                else:
                    self.assertIn(history.status_code, (401, 403))

    def test_stale_orders_exclude_started_or_finished_fulfillment(self):
        old = datetime.now(timezone.utc) - timedelta(hours=1)
        with self.Session() as db:
            for key, occupancy_status, actual_start, actual_end in [
                ('stale-unstarted', None, None, None),
                ('stale-waiting', 'waiting_service', None, None),
                ('stale-started', 'in_service', old, None),
                ('stale-finished', 'released', old, old),
            ]:
                db.add(SelectionSession(
                    id=key, access_token_hash='synthetic', store_id=self.store.id,
                    customer_id=self.user.id, status='confirmed', source='personal_qr',
                    items=[{'name': 'Test service'}], diy_preferences={}, created_at=old,
                ))
                db.flush()
                if occupancy_status:
                    db.add(PositionOccupancy(
                        store_id=self.store.id, room_id=self.room.id, selection_session_id=key,
                        serviced_by_technician_id=self.tech.id, status=occupancy_status,
                        actual_start_at=actual_start, actual_service_end_at=actual_end,
                    ))
            db.add(SelectionSession(
                id='fresh-order', access_token_hash='synthetic', store_id=self.store.id,
                customer_id=self.user.id, status='confirmed', source='personal_qr',
                items=[{'name': 'Test service'}], diy_preferences={},
            ))
            db.commit()

        workbench = self.client.get('/api/v1/admin/v2/manager/workbench', headers=self.headers)
        self.assertEqual(workbench.status_code, 200, workbench.text)
        stale_attention = next(item for item in workbench.json()['attention'] if item['key'] == 'stale_order')
        self.assertEqual(stale_attention['count'], 2)
        listing = self.client.get('/api/v1/admin/v2/selection-sessions?stale_only=true&active_only=true', headers=self.headers)
        self.assertEqual(listing.status_code, 200, listing.text)
        self.assertEqual({item['id'] for item in listing.json()['items']}, {'stale-unstarted', 'stale-waiting'})

    def test_service_anomalies_only_report_provable_current_model_breaks(self):
        with self.Session() as db:
            db.add(SelectionSession(
                id='anomaly-cancelled', access_token_hash='synthetic', store_id=self.store.id,
                customer_id=self.user.id, status='cancelled', source='personal_qr',
                items=[], diy_preferences={},
            ))
            db.add(SelectionSession(
                id='anomaly-valid', access_token_hash='synthetic', store_id=self.store.id,
                customer_id=self.user.id, status='confirmed', source='personal_qr',
                items=[], diy_preferences={},
            ))
            db.flush()
            db.add_all([
                PositionOccupancy(store_id=self.store.id, room_id=self.room.id, selection_session_id='anomaly-cancelled', status='waiting_service'),
                PositionOccupancy(store_id=self.store.id, room_id=self.room.id, selection_session_id='anomaly-valid', status='waiting_service'),
            ])
            db.commit()
        response = self.client.get('/api/v1/admin/v2/service-anomalies', headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['total'], 1)
        self.assertEqual(body['items'][0]['selection_session_id'], 'anomaly-cancelled')
        self.assertEqual(body['items'][0]['reason'], 'inactive_selection')
        self.assertIn('选单', body['items'][0]['label'])
        workbench = self.client.get('/api/v1/admin/v2/manager/workbench', headers=self.headers)
        self.assertEqual(workbench.status_code, 200, workbench.text)
        anomaly_attention = next(item for item in workbench.json()['attention'] if item['key'] == 'service_anomaly')
        self.assertEqual(anomaly_attention['count'], 1)
        first_sync = self.client.post('/api/v1/admin/v2/service-anomalies/sync', headers=self.headers)
        self.assertEqual(first_sync.status_code, 200, first_sync.text)
        self.assertEqual(first_sync.json()['created'], 1)
        second_sync = self.client.post('/api/v1/admin/v2/service-anomalies/sync', headers=self.headers)
        self.assertEqual(second_sync.json()['created'], 0)
        self.assertEqual(second_sync.json()['updated'], 1)
        unresolved = self.client.get('/api/v1/admin/exceptions?status=unresolved', headers=self.headers).json()
        matching = [row for row in unresolved['items'] if row['exception_type'] == 'service_inactive_selection']
        self.assertEqual(len(matching), 1)
        self.assertIn('选单', matching[0]['title'])
        self.assertEqual(workbench.json()['summary']['service_anomalies'], 1)
        self.assertEqual(self.client.get('/api/v1/admin/v2/service-anomalies', headers=self.worker_headers).status_code, 403)

    def test_unassigned_services_list_matches_workbench_count(self):
        with self.Session() as db:
            db.add(SelectionSession(
                id='unassigned-list-1', access_token_hash='synthetic', store_id=self.store.id,
                customer_id=self.user.id, status='confirmed', source='personal_qr',
                items=[{'name': '合成项目', 'quantity': 2}], diy_preferences={},
            ))
            db.flush()
            db.add(PositionOccupancy(
                store_id=self.store.id, room_id=self.room.id, selection_session_id='unassigned-list-1',
                status='waiting_service',
            ))
            db.commit()
        response = self.client.get('/api/v1/admin/v2/manager/unassigned-services', headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['total'], 1)
        self.assertEqual(body['items'][0]['room_name'], self.room.customer_label or self.room.name)
        self.assertEqual(body['items'][0]['items'][0]['name'], '合成项目')
        self.assertEqual(body['items'][0]['items'][0]['quantity'], 2)
        workbench = self.client.get('/api/v1/admin/v2/manager/workbench', headers=self.headers).json()
        self.assertEqual(workbench['summary']['unassigned_service'], body['total'])
        self.assertEqual(self.client.get('/api/v1/admin/v2/manager/unassigned-services', headers=self.worker_headers).status_code, 403)

    def test_manager_service_orders_filter_by_current_status(self):
        now = datetime.now(timezone.utc)
        with self.Session() as db:
            for key, occupancy_status, tech_id, ended in [
                ('orders-waiting', 'waiting_service', None, None),
                ('orders-in-service', 'in_service', self.tech.id, None),
                ('orders-completed', 'post_service_present', self.tech.id, now),
            ]:
                db.add(SelectionSession(
                    id=key, access_token_hash='synthetic', store_id=self.store.id,
                    customer_id=self.user.id, status='confirmed', source='personal_qr',
                    items=[{'name': '合成项目', 'quantity': 1}], diy_preferences={},
                ))
                db.flush()
                db.add(PositionOccupancy(
                    store_id=self.store.id, room_id=self.room.id, selection_session_id=key,
                    serviced_by_technician_id=tech_id, status=occupancy_status,
                    actual_service_end_at=ended,
                ))
            db.commit()
        for status, expected in [('waiting_service', 1), ('in_service', 1), ('completed', 1)]:
            response = self.client.get(f'/api/v1/admin/v2/manager/service-orders?status={status}', headers=self.headers)
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            self.assertEqual(body['status'], status)
            self.assertEqual(body['total'], expected)
            if status == 'waiting_service':
                self.assertIsNone(body['items'][0]['technician_name'])
            if status == 'in_service':
                self.assertEqual(body['items'][0]['technician_name'], self.tech.name)
        self.assertEqual(self.client.get('/api/v1/admin/v2/manager/service-orders', headers=self.worker_headers).status_code, 403)

    def test_manager_cannot_use_technician_history_and_worker_cannot_read_manager_todos(self):
        self.assertEqual(self.client.get('/api/v1/admin/v2/manager/workbench', headers=self.worker_headers).status_code, 403)
        self.assertEqual(self.client.get('/api/v1/admin/exceptions?status=unresolved', headers=self.worker_headers).status_code, 403)
        self.assertEqual(self.client.get('/api/v1/technician/service-history?record_status=pending', headers=self.headers).status_code, 403)


if __name__ == '__main__':
    unittest.main()
