"""Daily operations retry and search contracts; all data is synthetic."""
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.api.admin import create_staff_token
from app.db.session import Base, get_db
from app.main import app
from app.models import AuditLog, Staff, Store, OperationalException, VisitFeedback, ServiceFeedback, SelectionSession, SelectionRevision, ServiceLine

class AdminDailyOperationsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        with self.Session() as db:
            db.add_all([Store(id=1,store_code='daily-one',name='Synthetic one',address='Test'),Store(id=2,store_code='daily-two',name='Synthetic two',address='Test')]); db.flush()
            rows=[Staff(username='hq',name='HQ',role='admin',store_id=None,password_hash='unused'),Staff(username='manager_one',name='Alice Manager',role='manager',store_id=1,password_hash='unused'),Staff(username='worker_one',name='Alice Worker',role='staff',store_id=1,password_hash='unused'),Staff(username='manager_two',name='Bob Manager',role='manager',store_id=2,password_hash='unused')]
            db.add_all(rows); db.flush(); self.ids={x.username:x.id for x in rows}
            db.add(SelectionSession(id='daily-one',store_id=1,access_token_hash='synthetic',status='confirmed',items=[],diy_preferences={})); db.flush()
            db.add_all([OperationalException(id=1,store_id=1,exception_type='missing_order',dedupe_key='daily',title='Synthetic',detail={},entity_type='selection_session',entity_id='daily-one'),VisitFeedback(id=1,store_id=1,source='store_qr',identity_hash='synthetic',idempotency_key_hash='synthetic',request_fingerprint='synthetic',rating=2,note='Synthetic'),ServiceFeedback(id=1,store_id=1,selection_session_id='daily-one',rating=2,note='Synthetic')]); db.commit()
        def override():
            with self.Session() as db: yield db
        app.dependency_overrides[get_db]=override
        self.client=TestClient(app)
        self.h={name:{'Authorization':'Bearer '+create_staff_token(id_, 'admin' if name=='hq' else 'manager' if 'manager' in name else 'staff')} for name,id_ in self.ids.items()}
    def tearDown(self):
        self.client.close();app.dependency_overrides.clear();self.engine.dispose()
    def audit_count(self, action):
        with self.Session() as db:return db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action==action))
    def test_staff_combined_search_literal_wildcards_and_role_gate(self):
        r=self.client.get('/api/v1/admin/v2/staff',headers=self.h['hq'],params={'name':'alice','username':'MANAGER_','role':'manager','store_id':1})
        self.assertEqual(r.status_code,200);self.assertEqual(r.json()['total'],1);self.assertEqual(r.json()['items'][0]['username'],'manager_one')
        r=self.client.get('/api/v1/admin/v2/staff',headers=self.h['hq'],params={'name':'%'})
        self.assertEqual(r.json()['total'],0)
        self.assertEqual(self.client.get('/api/v1/admin/v2/staff?role=admin',headers=self.h['hq']).status_code,422)
        self.assertEqual(self.client.get('/api/v1/admin/v2/staff?name=Alice',headers=self.h['manager_one']).status_code,403)
    def test_assignment_and_resolution_retries_preserve_audit(self):
        base='/api/v1/admin/exceptions/1';h=self.h['manager_one']
        for _ in range(2):self.assertEqual(self.client.post(base+'/assign',headers=h,json={}).status_code,200)
        self.assertEqual(self.audit_count('assign_operational_exception'),1)
        self.assertEqual(self.client.post(base+'/resolve',headers=self.h['manager_two'],json={'resolution_note':'Must reject'}).status_code,404)
        self.assertEqual(self.client.post(base+'/resolve',headers=h,json={'resolution_note':'Verified synthetic result'}).status_code,200)
        self.assertEqual(self.client.post(base+'/resolve',headers=h,json={'resolution_note':'Overwrite attempt'}).status_code,409)
        self.assertEqual(self.client.post(base+'/assign',headers=h,json={}).status_code,409)
        self.assertEqual(self.audit_count('resolve_operational_exception'),1)
        row=self.client.get('/api/v1/admin/exceptions?status=resolved',headers=h).json()['items'][0]
        self.assertEqual(row['resolution_note'],'Verified synthetic result')
    def test_feedback_state_note_and_retry_for_both_types(self):
        for kind in ['visit_feedback','service_review']:
            path=f'/api/v1/admin/v2/feedback/{kind}/1';h=self.h['manager_one']
            payload={'follow_up_status':'resolved','follow_up_note':'Verified together'}
            first=self.client.patch(path,headers=h,json=payload);second=self.client.patch(path,headers=h,json=payload)
            self.assertEqual(first.status_code,200);self.assertEqual({k:v for k,v in first.json().items() if k != 'followed_up_at'}, {k:v for k,v in second.json().items() if k != 'followed_up_at'});self.assertEqual(first.json()['followed_up_at'].replace('+00:00',''), second.json()['followed_up_at'].replace('+00:00',''))
            read=self.client.get(path,headers=h).json();self.assertEqual(read['follow_up_note'],payload['follow_up_note']);self.assertEqual(read['follow_up_status'],'resolved')
            self.assertEqual(self.client.patch(path,headers=self.h['manager_two'],json=payload).status_code,404)
            self.assertEqual(self.client.patch(path,headers=self.h['worker_one'],json=payload).status_code,403)
        self.assertEqual(self.audit_count('update_feedback_follow_up'),2)
    def test_legacy_feedback_retry_is_noop(self):
        path='/api/v1/admin/v2/feedback/1';h=self.h['manager_one'];payload={'follow_up_status':'in_progress','follow_up_note':'Legacy compatibility'}
        first=self.client.patch(path,headers=h,json=payload);second=self.client.patch(path,headers=h,json=payload)
        self.assertEqual(first.status_code,200);self.assertEqual({k:v for k,v in first.json().items() if k != 'followed_up_at'}, {k:v for k,v in second.json().items() if k != 'followed_up_at'});self.assertEqual(first.json()['followed_up_at'].replace('+00:00',''), second.json()['followed_up_at'].replace('+00:00',''));self.assertEqual(self.audit_count('update_feedback_follow_up'),1)

    def test_current_execution_lines_prevent_false_missing_order(self):
        with self.Session() as db:
            db.add_all([
                SelectionSession(id='fulfilled',store_id=1,access_token_hash='synthetic',status='confirmed',items=[],diy_preferences={}),
                SelectionSession(id='wrong-revision',store_id=1,access_token_hash='synthetic',status='confirmed',items=[],diy_preferences={}),
                SelectionSession(id='other-store',store_id=2,access_token_hash='synthetic',status='confirmed',items=[],diy_preferences={}),
            ]);db.flush()
            db.add(SelectionRevision(id='confirmed-revision',selection_session_id='fulfilled',revision_no=1,state='confirmed',idempotency_key='test',snapshot={}));db.flush()
            db.add_all([
                ServiceLine(id='fulfilled-line',selection_session_id='fulfilled',selection_revision_id='confirmed-revision',state='pending',snapshot={}),
                ServiceLine(id='wrong-line',selection_session_id='wrong-revision',selection_revision_id='confirmed-revision',state='pending',snapshot={}),
            ]);db.commit()
        response=self.client.get('/api/v1/admin/order-reconciliation',headers=self.h['manager_one'])
        self.assertEqual(response.status_code,200)
        missing={row['selection_session_id'] for row in response.json()['items'] if row['type']=='missing_order'}
        self.assertEqual(missing,{'daily-one','wrong-revision'})
        synced=self.client.post('/api/v1/admin/order-reconciliation/sync',headers=self.h['manager_one'])
        self.assertEqual(synced.status_code,200)
        with self.Session() as db:
            self.assertIsNone(db.scalar(select(OperationalException).where(OperationalException.entity_id=='fulfilled')))
