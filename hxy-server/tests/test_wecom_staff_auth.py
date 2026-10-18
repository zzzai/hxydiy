import os
import json
import logging
import threading
import unittest
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

from httpx import Cookies
from fastapi import Depends, FastAPI, Header
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.engine import make_url

from app.api.admin import create_staff_token
from app.core.config import settings
from app.db.session import Base, get_db
from app.domain.staff_workspaces import resolve_staff_context
from app.models import Staff, Store, Technician
from app.models.staff_external_identity import StaffExternalIdentity, StaffOAuthAttempt


class WecomRouteRegistrationTests(unittest.TestCase):
    def test_disabled_authorize_is_registered(self):
        from app.main import app
        with TestClient(app) as client:
            response = client.post("/api/v1/auth/wecom/authorize", json={"entry_nonce": "n" * 32})
        self.assertEqual(response.status_code, 503, response.text)


class WecomStaffAuthTests(unittest.TestCase):
    def setUp(self):
        url = os.environ.get("WECOM_TEST_DATABASE_URL")
        self.postgres = bool(url)
        if url:
            if make_url(url).database != "wecom_test" or settings.environment != "test":
                raise RuntimeError("An isolated wecom_test database and test environment are required")
            bootstrap = create_engine(url)
            with bootstrap.begin() as db:
                db.execute(text("CREATE SCHEMA IF NOT EXISTS auth_contract"))
            bootstrap.dispose()
            self.engine = create_engine(url, connect_args={"options": "-csearch_path=auth_contract"})
            with self.engine.connect() as db:
                self.assertEqual(db.scalar(text("SELECT current_schema()")), "auth_contract")
        else:
            self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        self.app = FastAPI()
        from app.api.wecom_staff import router
        from app.services.wecom_staff import get_wecom_provider
        self.provider_dependency = get_wecom_provider
        self.app.include_router(router, prefix="/api/v1")

        def database():
            with self.sessions() as db:
                yield db

        @self.app.get("/protected")
        def protected(authorization: str = Header(), db: Session = Depends(get_db)):
            context = resolve_staff_context(authorization.removeprefix("Bearer "), db)
            return {"staff_id": context.id, "technician_id": context.technician_id}

        self.app.dependency_overrides[get_db] = database
        self.provider = SyntheticProvider()
        self.app.dependency_overrides[get_wecom_provider] = lambda: self.provider
        self.provider_patch = patch("app.services.wecom_staff.get_wecom_provider", return_value=self.provider)
        self.provider_patch.start()
        self.client = TestClient(self.app, base_url="https://testserver")
        self.config = patch.multiple(settings, wecom_staff_enabled=True, wecom_corp_id="synthetic-corp", wecom_agent_id="1000002", wecom_agent_secret="synthetic-secret", wecom_callback_url="https://testserver/api/v1/auth/wecom/callback", h5_public_base_url="https://testserver/")
        self.config.start()
        with self.sessions() as db:
            store = Store(store_code="wecom-test", name="Synthetic store", address="Synthetic")
            db.add(store)
            db.flush()
            tech = Technician(store_id=store.id, code="wecom-test-tech", name="Synthetic", status="available")
            db.add(tech)
            db.flush()
            staff = Staff(username="wecom-test", name="Synthetic", password_hash="unused", role="technician", store_id=store.id, technician_id=tech.id, status="active")
            db.add(staff)
            db.commit()
            self.staff_id, self.store_id, self.tech_id = staff.id, store.id, tech.id

    def tearDown(self):
        self.client.close()
        self.provider_patch.stop()
        self.config.stop()
        if self.postgres:
            with self.engine.begin() as db:
                self.assertEqual(db.scalar(text("SELECT current_schema()")), "auth_contract")
                db.execute(text("DROP SCHEMA auth_contract CASCADE"))
        self.engine.dispose()

    def bind(self):
        from app.models.staff_external_identity import StaffExternalIdentity
        with self.sessions() as db:
            row = StaffExternalIdentity(provider="wecom", corp_id="synthetic-corp", userid="USER-1", staff_id=self.staff_id, technician_id=self.tech_id, store_id=self.store_id)
            db.add(row)
            db.commit()
            return row.id

    def authorize(self, client=None, nonce="n" * 32):
        response = (client or self.client).post("/api/v1/auth/wecom/authorize", json={"entry_nonce": nonce})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        state = parse_qs(urlparse(body["authorization_url"]).query)["state"][0]
        self.assertEqual(body["expires_in"], 300)
        return body["attempt_id"], state

    def callback(self, state, client=None):
        return (client or self.client).get("/api/v1/auth/wecom/callback", params={"code": "synthetic-code", "state": state}, follow_redirects=False)

    def exchange(self, attempt, nonce="n" * 32, client=None):
        return (client or self.client).post("/api/v1/auth/wecom/exchange", json={"attempt_id": attempt, "entry_nonce": nonce})

    def login(self):
        attempt, state = self.authorize()
        response = self.callback(state)
        self.assertEqual(response.status_code, 303, response.text)
        self.assertEqual(response.headers["location"], "https://testserver/technician/wecom/complete")
        response = self.exchange(attempt)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["token"]

    def protected(self, token):
        return self.client.get("/protected", headers={"Authorization": f"Bearer {token}"})

    def test_wecom_routes_exist_and_are_disabled_by_default(self):
        with patch.object(settings, "wecom_staff_enabled", False):
            response = self.client.post("/api/v1/auth/wecom/authorize", json={"entry_nonce": "n" * 32})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "WECOM_DISABLED")

    def test_browser_bound_one_use_exchange_returns_only_resolved_technician(self):
        self.bind()
        attempt, state = self.authorize()
        cookie_headers = self.client.cookies
        self.assertTrue(any(name.startswith("wecom_attempt_") for name in cookie_headers.keys()))
        self.assertEqual(self.callback(state).status_code, 303)
        replay = self.callback(state)
        self.assertEqual(replay.status_code, 303)
        response = self.exchange(attempt)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["staff"], {"id": self.staff_id, "name": "Synthetic", "role": "technician", "store_id": self.store_id, "technician_id": self.tech_id})
        self.assertEqual(body["auth_method"], "wecom")
        self.assertEqual(self.protected(body["token"]).status_code, 200)
        self.assertEqual(self.exchange(attempt).status_code, 401)

    def test_callback_cannot_be_consumed_by_another_browser(self):
        self.bind()
        attempt, state = self.authorize()
        with TestClient(self.app, base_url="https://testserver") as stranger:
            self.assertEqual(self.callback(state, stranger).status_code, 303)
            self.assertEqual(self.exchange(attempt, client=stranger).status_code, 401)
        self.assertEqual(self.callback(state).status_code, 303)
        self.assertEqual(self.exchange(attempt).status_code, 200)

    def test_each_browser_bound_attempt_requires_its_own_nonce(self):
        self.bind()
        old, old_state = self.authorize(nonce="o" * 32)
        current, state = self.authorize(nonce="c" * 32)
        self.callback(old_state)
        self.assertEqual(self.exchange(old, nonce="c" * 32).status_code, 401)
        self.callback(state)
        self.assertEqual(self.exchange(current, nonce="w" * 32).status_code, 401)
        self.assertEqual(self.exchange(current, nonce="c" * 32).status_code, 200)

    def test_late_old_authorize_response_cannot_replace_new_attempt_cookie(self):
        self.bind()
        old = self.client.post("/api/v1/auth/wecom/authorize", json={"entry_nonce": "o" * 32})
        current = self.client.post("/api/v1/auth/wecom/authorize", json={"entry_nonce": "c" * 32})
        browser = Cookies()
        browser.extract_cookies(current)
        browser.extract_cookies(old)
        self.client.cookies.clear()
        self.client.cookies.update(browser)
        body = current.json()
        state = parse_qs(urlparse(body["authorization_url"]).query)["state"][0]
        self.callback(state)
        self.assertEqual(self.exchange(body["attempt_id"], nonce="c" * 32).status_code, 200)

    def test_late_old_exchange_response_cannot_delete_new_attempt_cookie(self):
        self.bind()
        old = self.client.post("/api/v1/auth/wecom/authorize", json={"entry_nonce": "o" * 32})
        browser = Cookies()
        browser.extract_cookies(old)
        old_body = old.json()
        old_state = parse_qs(urlparse(old_body["authorization_url"]).query)["state"][0]
        self.callback(old_state)
        old_exchange = self.exchange(old_body["attempt_id"], nonce="o" * 32)
        self.assertEqual(old_exchange.status_code, 200)
        current = self.client.post("/api/v1/auth/wecom/authorize", json={"entry_nonce": "c" * 32})
        browser.extract_cookies(current)
        browser.extract_cookies(old_exchange)
        self.client.cookies.clear()
        self.client.cookies.update(browser)
        current_body = current.json()
        state = parse_qs(urlparse(current_body["authorization_url"]).query)["state"][0]
        self.callback(state)
        self.assertEqual(self.exchange(current_body["attempt_id"], nonce="c" * 32).status_code, 200)

    def test_state_nonce_browser_are_hashed_and_expiry_denies_callback(self):
        from app.models.staff_external_identity import StaffOAuthAttempt
        self.bind()
        attempt, state = self.authorize()
        with self.sessions() as db:
            row = db.get(StaffOAuthAttempt, attempt)
            self.assertNotEqual(row.state_hash, state)
            self.assertNotEqual(row.nonce_hash, "n" * 32)
            self.assertEqual(len(row.state_hash), 64)
            self.assertEqual(len(row.browser_hash), 64)
            row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        self.callback(state)
        self.assertEqual(self.exchange(attempt).status_code, 401)

    def test_unbound_identity_does_not_match_staff_name_or_phone(self):
        attempt, state = self.authorize()
        self.callback(state)
        self.assertEqual(self.exchange(attempt).status_code, 401)

    def test_provider_membership_failure_burns_callback_without_leaking_details(self):
        from app.services.wecom_staff import WecomProviderError
        self.bind()
        attempt, state = self.authorize()
        self.provider.failure = WecomProviderError()
        response = self.callback(state)
        self.assertEqual(response.status_code, 303)
        self.assertNotIn("synthetic-code", response.headers["location"])
        self.provider.failure = None
        self.callback(state)
        self.assertEqual(self.exchange(attempt).status_code, 401)

    def test_unlink_revokes_wecom_only_and_binding_version_revokes_ready_attempt(self):
        from app.models.staff_external_identity import StaffExternalIdentity
        identity_id = self.bind()
        token = self.login()
        with self.sessions() as db:
            staff = db.get(Staff, self.staff_id)
            password_token = create_staff_token(staff.id, "technician", staff.credentials_version)
            identity = db.get(StaffExternalIdentity, identity_id)
            identity.status = "disabled"
            identity.binding_version += 1
            db.commit()
        self.assertEqual(self.protected(token).status_code, 401)
        self.assertEqual(self.protected(password_token).status_code, 200)

    def test_stale_provider_proof_is_reverified_and_outage_denies(self):
        from app.models.staff_external_identity import StaffExternalIdentity
        from app.services.wecom_staff import WecomProviderError
        identity_id = self.bind()
        token = self.login()
        with self.sessions() as db:
            db.get(StaffExternalIdentity, identity_id).provider_verified_at = datetime.now(timezone.utc) - timedelta(seconds=301)
            db.commit()
        self.provider.failure = WecomProviderError()
        self.assertEqual(self.protected(token).status_code, 401)
        self.provider.failure = None
        with patch("app.services.wecom_staff.get_wecom_provider", return_value=self.provider):
            self.assertEqual(self.protected(token).status_code, 200)

    def test_department_member_scope_removal_denies_login_and_expired_proof(self):
        cases = [
            {"errcode": 48002, "errmsg": "synthetic permission denied"},
            {"errcode": 0, "userid": "another-user", "status": 1},
        ]
        identity_id = self.bind()
        for revoked_member in cases:
            with self.subTest(member=revoked_member):
                responses = WecomProviderTests().responses()
                responses["/cgi-bin/agent/get"]["allow_userinfos"] = {"user": []}
                provider, transport, requests = WecomProviderTests().provider(responses)
                self.app.dependency_overrides[self.provider_dependency] = lambda: provider
                with patch("app.services.wecom_staff.urlopen", side_effect=transport), patch("app.services.wecom_staff.get_wecom_provider", return_value=provider):
                    token = self.login()
                    responses["/cgi-bin/user/get"] = revoked_member
                    with self.sessions() as db:
                        row = db.get(StaffExternalIdentity, identity_id)
                        row.provider_verified_at = datetime.now(timezone.utc) - timedelta(seconds=300)
                        stale_proof = row.provider_verified_at
                        db.commit()
                    self.assertEqual(self.protected(token).status_code, 401)
                    with self.sessions() as db:
                        proof = db.get(StaffExternalIdentity, identity_id).provider_verified_at
                        self.assertEqual(proof.replace(tzinfo=timezone.utc), stale_proof)
                    attempt, state = self.authorize()
                    self.assertEqual(self.callback(state).status_code, 303)
                    self.assertEqual(self.exchange(attempt).status_code, 401)
                self.assertEqual(requests[0], ("/cgi-bin/gettoken", {"corpid": ["synthetic-corp"], "corpsecret": ["synthetic-secret"]}))
                self.assertTrue(all(query.get("access_token") == ["synthetic-provider-token"] for path, query in requests if path != "/cgi-bin/gettoken"))

    def test_changed_staff_version_or_resigned_technician_invalidates_wecom(self):
        self.bind()
        token = self.login()
        with self.sessions() as db:
            db.get(Technician, self.tech_id).status = "resigned"
            db.commit()
        self.assertEqual(self.protected(token).status_code, 401)

    def test_binding_version_change_after_callback_denies_exchange(self):
        identity_id = self.bind()
        attempt, state = self.authorize()
        self.callback(state)
        with self.sessions() as db:
            identity = db.get(StaffExternalIdentity, identity_id)
            identity.binding_version += 1
            db.commit()
        self.assertEqual(self.exchange(attempt).status_code, 401)

    def test_unlink_then_reenable_cannot_resurrect_old_wecom_session(self):
        identity_id = self.bind()
        token = self.login()
        with self.sessions() as db:
            identity = db.get(StaffExternalIdentity, identity_id)
            identity.status = "disabled"
            db.commit()
            identity.status = "active"
            db.commit()
        self.assertEqual(self.protected(token).status_code, 401)

    def test_rebinding_identity_to_another_staff_cannot_resurrect_old_session(self):
        identity_id = self.bind()
        token = self.login()
        with self.sessions() as db:
            tech = Technician(store_id=self.store_id, code="second-tech", name="Second")
            db.add(tech)
            db.flush()
            staff = Staff(username="second-staff", password_hash="unused", name="Second", role="technician", store_id=self.store_id, technician_id=tech.id)
            db.add(staff)
            db.flush()
            identity = db.get(StaffExternalIdentity, identity_id)
            identity.staff_id, identity.technician_id = staff.id, tech.id
            db.commit()
        self.assertEqual(self.protected(token).status_code, 401)

    def test_two_stale_database_sessions_advance_binding_versions_monotonically(self):
        identity_id = self.bind()
        with self.sessions() as first, self.sessions() as second:
            first_identity = first.get(StaffExternalIdentity, identity_id)
            second_identity = second.get(StaffExternalIdentity, identity_id)
            self.assertEqual((first_identity.binding_version, second_identity.binding_version), (1, 1))
            first_identity.userid = "user-2"
            first.commit()
            self.assertEqual(first_identity.binding_version, 2)
            self.provider.userid = "user-2"
            first_token = self.login()
            self.assertEqual(self.protected(first_token).status_code, 200)
            second_identity.userid = "user-3"
            second.commit()
            self.assertEqual(second_identity.binding_version, 3)
        self.provider.userid = "user-3"
        second_token = self.login()
        self.assertEqual(self.protected(second_token).status_code, 200)
        self.assertEqual(self.protected(first_token).status_code, 401)
        with self.sessions() as db:
            staff = db.get(Staff, self.staff_id)
            self.assertEqual(staff.credentials_version, 1)
            password_token = create_staff_token(staff.id, staff.role, staff.credentials_version)
        self.assertEqual(self.protected(password_token).status_code, 200)

    def test_different_external_subject_cannot_share_active_staff_binding(self):
        self.bind()
        with self.sessions() as db:
            db.add(StaffExternalIdentity(provider="wecom", corp_id="synthetic-corp", userid="different-user", staff_id=self.staff_id, technician_id=self.tech_id, store_id=self.store_id))
            with self.assertRaises(IntegrityError):
                db.commit()

    def test_staff_credential_version_change_revokes_wecom(self):
        self.bind()
        token = self.login()
        with self.sessions() as db:
            db.get(Staff, self.staff_id).credentials_version += 1
            db.commit()
        self.assertEqual(self.protected(token).status_code, 401)

    def test_staff_store_mismatch_revokes_wecom(self):
        self.bind()
        token = self.login()
        with self.sessions() as db:
            store = Store(store_code="other", name="Other", address="Synthetic")
            db.add(store)
            db.flush()
            db.get(Staff, self.staff_id).store_id = store.id
            db.commit()
        self.assertEqual(self.protected(token).status_code, 401)

    def test_off_duty_technician_cannot_complete_wecom_entry(self):
        self.bind()
        with self.sessions() as db:
            db.get(Technician, self.tech_id).status = "off"
            db.commit()
        attempt, state = self.authorize()
        self.callback(state)
        self.assertEqual(self.exchange(attempt).status_code, 401)

    def test_pg_concurrent_callback_and_exchange_complete_once(self):
        if not self.postgres:
            self.skipTest("Requires isolated PostgreSQL")
        self.bind()
        attempt, state = self.authorize()
        cookies = dict(self.client.cookies)
        barrier = threading.Barrier(2)

        def callback():
            with TestClient(self.app, base_url="https://testserver") as client:
                client.cookies.update(cookies)
                barrier.wait(timeout=5)
                return self.callback(state, client).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(lambda _: callback(), range(2))), [303, 303])
        self.assertEqual(self.provider.exchanges, 1)
        barrier = threading.Barrier(2)

        def exchange():
            with TestClient(self.app, base_url="https://testserver") as client:
                client.cookies.update(cookies)
                barrier.wait(timeout=5)
                return self.exchange(attempt, client=client).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(lambda _: exchange(), range(2)))
        self.assertEqual(sorted(statuses), [200, 401])
        with self.sessions() as db:
            self.assertEqual(db.get(StaffOAuthAttempt, attempt).status, "used")

    def test_external_callback_origin_is_rejected_before_attempt_created(self):
        with patch.object(settings, "wecom_callback_url", "https://evil.example/api/v1/auth/wecom/callback"):
            response = self.client.post("/api/v1/auth/wecom/authorize", json={"entry_nonce": "n" * 32})
        self.assertEqual(response.status_code, 503)

    def test_trailing_slash_callback_also_cleans_redirect_location(self):
        self.bind()
        attempt, state = self.authorize()
        response = self.client.get("/api/v1/auth/wecom/callback/", params={"code": "synthetic-code", "state": state}, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "https://testserver/technician/wecom/complete")
        self.assertEqual(self.exchange(attempt).status_code, 200)

    def test_userid_case_and_active_staff_binding_are_database_unique(self):
        from app.models.staff_external_identity import StaffExternalIdentity
        self.bind()
        with self.sessions() as db:
            row = db.scalar(select(StaffExternalIdentity))
            self.assertEqual(row.userid, "user-1")
            row.status = "disabled"
            db.commit()
            db.add(StaffExternalIdentity(provider="wecom", corp_id="synthetic-corp", userid="user-1", staff_id=self.staff_id, technician_id=self.tech_id, store_id=self.store_id))
            with self.assertRaises(IntegrityError):
                db.commit()


class SyntheticProvider:
    def __init__(self):
        self.failure = None
        self.exchanges = 0
        self.userid = "user-1"

    def exchange_code(self, code):
        self.exchanges += 1
        if self.failure:
            raise self.failure
        if code != "synthetic-code":
            raise AssertionError("Unexpected synthetic code")
        return self.userid.upper()

    def verify_member(self, userid):
        if self.failure:
            raise self.failure
        if userid != self.userid:
            raise AssertionError("User identity must be canonical")


class WecomProviderTests(unittest.TestCase):
    def provider(self, responses):
        from app.services.wecom_staff import WecomProvider
        requests = []

        def open_request(request, timeout):
            from io import BytesIO
            parsed = urlparse(request.full_url)
            query = parse_qs(parsed.query)
            requests.append((parsed.path, query))
            response = responses[parsed.path]
            return BytesIO(json.dumps(response).encode())

        return WecomProvider(), open_request, requests

    def responses(self):
        return {
            "/cgi-bin/gettoken": {"errcode": 0, "access_token": "synthetic-provider-token", "expires_in": 7200},
            "/cgi-bin/auth/getuserinfo": {"errcode": 0, "userid": "UsEr-1"},
            "/cgi-bin/user/get": {"errcode": 0, "userid": "USER-1", "status": 1},
            "/cgi-bin/agent/get": {"errcode": 0, "agentid": 1000002, "close": 0, "allow_userinfos": {"user": [{"userid": "USER-1"}]}, "allow_partys": {"partyid": [1]}},
        }

    def test_official_lowercase_userid_active_member_and_explicit_visible_user(self):
        provider, transport, requests = self.provider(self.responses())
        with patch.multiple(settings, wecom_corp_id="synthetic-corp", wecom_agent_id="1000002", wecom_agent_secret="synthetic-secret"), patch("app.services.wecom_staff.urlopen", side_effect=transport):
            self.assertEqual(provider.exchange_code("synthetic-code"), "user-1")
            provider.verify_member("user-1")
            provider.verify_member("user-1")
        self.assertEqual([path for path, _ in requests].count("/cgi-bin/gettoken"), 1)
        self.assertEqual(requests[1][1], {"access_token": ["synthetic-provider-token"], "code": ["synthetic-code"]})

    def test_department_visible_member_uses_same_app_token_without_directory_expansion(self):
        for individual_scope in ({"user": []}, None):
            with self.subTest(individual_scope=individual_scope):
                responses = self.responses()
                responses["/cgi-bin/agent/get"]["allow_userinfos"] = individual_scope
                provider, transport, requests = self.provider(responses)
                with patch.multiple(settings, wecom_corp_id="synthetic-corp", wecom_agent_id="1000002", wecom_agent_secret="synthetic-secret"), patch("app.services.wecom_staff.urlopen", side_effect=transport):
                    userid = provider.exchange_code("synthetic-code")
                    provider.verify_member(userid)
                self.assertEqual([path for path, _ in requests], ["/cgi-bin/gettoken", "/cgi-bin/auth/getuserinfo", "/cgi-bin/user/get", "/cgi-bin/agent/get"])
                self.assertEqual(requests[0][1], {"corpid": ["synthetic-corp"], "corpsecret": ["synthetic-secret"]})
                self.assertEqual(requests[2][1], {"access_token": ["synthetic-provider-token"], "userid": ["user-1"]})
                self.assertEqual(requests[3][1], {"access_token": ["synthetic-provider-token"], "agentid": ["1000002"]})

    def test_disabled_wrong_app_inactive_invisible_or_mismatched_member_deny(self):
        from app.services.wecom_staff import WecomProviderError
        mutations = [
            ("/cgi-bin/agent/get", {"errcode": 0, "agentid": 1000002, "close": 1, "allow_userinfos": {"user": [{"userid": "user-1"}]}}),
            ("/cgi-bin/agent/get", {"errcode": 0, "agentid": 1000009, "close": 0}),
            ("/cgi-bin/agent/get", {"errcode": 0, "agentid": 1000002}),
            ("/cgi-bin/user/get", {"errcode": 48002, "errmsg": "synthetic permission denied"}),
            ("/cgi-bin/user/get", {"errcode": 0, "userid": "another-user", "status": 1}),
            ("/cgi-bin/user/get", {"errcode": 0, "userid": "user-1", "status": 2}),
            ("/cgi-bin/auth/getuserinfo", {"errcode": 0, "UserId": "user-1"}),
        ]
        for endpoint, replacement in mutations:
            with self.subTest(endpoint=endpoint, response=replacement):
                responses = self.responses()
                responses[endpoint] = replacement
                provider, transport, _ = self.provider(responses)
                with patch.multiple(settings, wecom_corp_id="synthetic-corp", wecom_agent_id="1000002", wecom_agent_secret="synthetic-secret"), patch("app.services.wecom_staff.urlopen", side_effect=transport):
                    with self.assertRaises(WecomProviderError):
                        userid = provider.exchange_code("synthetic-code")
                        provider.verify_member(userid)

    def test_provider_failure_never_exposes_upstream_url_or_secret(self):
        from app.services.wecom_staff import WecomProvider, WecomProviderError
        from urllib.error import URLError
        with patch.multiple(settings, wecom_corp_id="synthetic-corp", wecom_agent_secret="synthetic-secret"), patch("app.services.wecom_staff.urlopen", side_effect=URLError("https://qyapi.weixin.qq.com/?corpsecret=synthetic-secret")):
            with self.assertRaises(WecomProviderError) as caught:
                WecomProvider().exchange_code("synthetic-code")
        self.assertEqual(str(caught.exception), "WeCom verification unavailable")
        self.assertIsNone(caught.exception.__cause__)

    def test_callback_access_log_strips_query_and_preserves_other_paths(self):
        from app.api.wecom_staff import CallbackAccessLogFilter
        record = logging.LogRecord("uvicorn.access", logging.INFO, "", 1, '%s - "%s %s HTTP/%s" %d', ("127.0.0.1", "GET", "/api/v1/auth/wecom/callback?code=synthetic-code&state=synthetic-state", "1.1", 303), None)
        CallbackAccessLogFilter().filter(record)
        self.assertEqual(record.getMessage(), '127.0.0.1 - "GET /api/v1/auth/wecom/callback HTTP/1.1" 303')
