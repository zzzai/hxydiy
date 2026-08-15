import unittest
from types import SimpleNamespace
from unittest import mock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.session import Base, get_db
from app.main import app
from app.models import CustomerVerificationCode, User
from app.services import aliyun_pnvs


class FakeDypnsClient:
    """内存版阿里云号码认证客户端：记录发送/校验调用，不真正联网。"""

    def __init__(self):
        self.sent_phones = []
        self.verify_calls = []
        self.valid_codes = {}
        self.send_exc = None
        self.verify_exc = None
        self.send_response_code = "OK"

    def send_sms_verify_code_with_options(self, request, runtime):
        if self.send_exc:
            raise self.send_exc
        self.sent_phones.append(request.phone_number)
        body = SimpleNamespace(code=self.send_response_code, message="OK", request_id="req-1")
        return SimpleNamespace(body=body)

    def check_sms_verify_code_with_options(self, request, runtime):
        if self.verify_exc:
            raise self.verify_exc
        self.verify_calls.append((request.phone_number, request.verify_code))
        code = "OK" if self.valid_codes.get(request.phone_number) == request.verify_code else "INVALID"
        body = SimpleNamespace(code=code, message="OK", request_id="req-2")
        return SimpleNamespace(body=body)


class H5AuthAliyunSmsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        cls.SessionLocal = sessionmaker(bind=cls.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(cls.engine)

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

    def setUp(self):
        self.patches = [
            mock.patch.object(settings, "aliyun_pnvs_access_key_id", "ak-test"),
            mock.patch.object(settings, "aliyun_pnvs_access_key_secret", "sk-test"),
            mock.patch.object(settings, "aliyun_pnvs_scheme_name", "FC-test"),
        ]
        for p in self.patches:
            p.start()
        self.fake = FakeDypnsClient()
        self._saved_client = aliyun_pnvs._client
        aliyun_pnvs._client = self.fake

    def tearDown(self):
        aliyun_pnvs._client = self._saved_client
        for p in reversed(self.patches):
            p.stop()

    def send_code(self, phone="13800138000"):
        response = self.client.post("/api/v1/auth/h5/send-code", json={"phone": phone})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_send_code_goes_through_aliyun_and_hides_code(self):
        result = self.send_code("13800138000")
        self.assertIsNone(result["debug_code"])
        self.assertTrue(result["sent"])
        self.assertEqual(self.fake.sent_phones, ["13800138000"])
        with self.SessionLocal() as db:
            record = db.scalar(select(CustomerVerificationCode).where(CustomerVerificationCode.phone == "13800138000"))
            self.assertTrue(record.code_hash.startswith("aliyun:"))

    def test_login_verifies_through_aliyun_and_creates_user(self):
        self.send_code("13900139000")
        self.fake.valid_codes["13900139000"] = "246810"
        response = self.client.post("/api/v1/auth/h5/login", json={"phone": "13900139000", "code": "246810"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.fake.verify_calls, [("13900139000", "246810")])
        with self.SessionLocal() as db:
            user = db.scalar(select(User).where(User.phone == "13900139000"))
            self.assertIsNotNone(user)
            record = db.scalar(select(CustomerVerificationCode).where(CustomerVerificationCode.phone == "13900139000"))
            self.assertIsNotNone(record.used_at)

    def test_login_wrong_code_is_limited(self):
        self.send_code("13700137000")
        self.fake.valid_codes["13700137000"] = "135790"
        for _ in range(5):
            response = self.client.post("/api/v1/auth/h5/login", json={"phone": "13700137000", "code": "000000"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("次数", response.json()["detail"])
        with self.SessionLocal() as db:
            record = db.scalar(select(CustomerVerificationCode).where(CustomerVerificationCode.phone == "13700137000"))
            self.assertEqual(record.attempts, 5)
            self.assertIsNone(record.used_at)

    def test_send_failure_returns_502(self):
        self.fake.send_exc = RuntimeError("network down")
        response = self.client.post("/api/v1/auth/h5/send-code", json={"phone": "13600136000"})
        self.assertEqual(response.status_code, 502)

    def test_verify_service_down_returns_502(self):
        self.send_code("13500135000")
        self.fake.verify_exc = RuntimeError("network down")
        response = self.client.post("/api/v1/auth/h5/login", json={"phone": "13500135000", "code": "123456"})
        self.assertEqual(response.status_code, 502)


if __name__ == "__main__":
    unittest.main()
