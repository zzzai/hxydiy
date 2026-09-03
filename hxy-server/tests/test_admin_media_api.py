import io
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import AuditLog, Staff, Store
from app.services.media_storage import MediaStorageError


class _FakeStorage:
    def __init__(self):
        self.put_calls = []
        self.delete_calls = []

    def put(self, object_key, content, content_type):
        self.put_calls.append((object_key, content, content_type))

    def delete(self, object_key):
        self.delete_calls.append(object_key)

    def url(self, object_key):
        return f"https://img.hexiaoyue.com/{object_key}"


class _FailingDeleteStorage(_FakeStorage):
    def delete(self, object_key):
        self.delete_calls.append(object_key)
        raise MediaStorageError("七牛云删除失败，HTTP 500")


class AdminMediaApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        cls.SessionLocal = sessionmaker(bind=cls.engine, expire_on_commit=False)
        Base.metadata.create_all(cls.engine)
        with cls.SessionLocal() as db:
            store = Store(store_code="media-store", name="媒体店", address="测试")
            other = Store(store_code="media-other", name="其他店", address="测试")
            db.add_all([store, other])
            db.flush()
            manager = Staff(username="media-manager", password_hash=hash_password("pass"), name="店长", role="admin", store_id=store.id, status="active")
            other_manager = Staff(username="media-other-manager", password_hash=hash_password("pass"), name="其他店长", role="admin", store_id=other.id, status="active")
            headquarters = Staff(username="media-headquarters", password_hash=hash_password("pass"), name="总部", role="admin", store_id=None, status="active")
            db.add_all([manager, other_manager, headquarters])
            db.commit()
            cls.manager_id, cls.other_manager_id, cls.headquarters_id = manager.id, other_manager.id, headquarters.id
        app.dependency_overrides[get_db] = cls._get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        app.dependency_overrides.pop(get_db, None)
        cls.engine.dispose()

    @classmethod
    def _get_db(cls):
        with cls.SessionLocal() as db:
            yield db

    @staticmethod
    def _headers(staff_id: int, role: str = "admin"):
        return {"Authorization": f"Bearer {create_staff_token(staff_id, role)}"}

    def test_manager_can_upload_image_and_response_contains_scoped_metadata(self):
        response = self.client.post(
            "/api/v1/admin/media",
            headers=self._headers(self.manager_id),
            files={"file": ("cover.png", io.BytesIO(b"png-bytes"), "image/png")},
            data={"purpose": "project_cover"},
        )
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["media_type"], "image")
        self.assertEqual(body["original_name"], "cover.png")
        self.assertEqual(body["purpose"], "project_cover")
        self.assertTrue(body["url"].startswith("/api/v1/admin/media/"))
        self.assertEqual(body["url"], f"/api/v1/admin/media/{body['id']}/content")
        with self.SessionLocal() as db:
            audit = db.scalar(select(AuditLog).where(AuditLog.entity_type == "media", AuditLog.action == "media_upload"))
            self.assertIsNotNone(audit)
            self.assertEqual(audit.store_id, body["store_id"])

    def test_upload_rejects_non_image_and_oversized_files(self):
        bad_type = self.client.post(
            "/api/v1/admin/media",
            headers=self._headers(self.manager_id),
            files={"file": ("payload.txt", io.BytesIO(b"text"), "text/plain")},
        )
        self.assertEqual(bad_type.status_code, 415)
        too_large = self.client.post(
            "/api/v1/admin/media",
            headers=self._headers(self.manager_id),
            files={"file": ("large.jpg", io.BytesIO(b"x" * (5 * 1024 * 1024 + 1)), "image/jpeg")},
        )
        self.assertEqual(too_large.status_code, 413)

    def test_regular_staff_cannot_upload_media(self):
        with self.SessionLocal() as db:
            staff = Staff(username="media-staff", password_hash=hash_password("pass"), name="员工", role="staff", store_id=1, status="active")
            db.add(staff)
            db.commit()
            staff_id = staff.id
        response = self.client.post(
            "/api/v1/admin/media",
            headers=self._headers(staff_id, "staff"),
            files={"file": ("cover.png", io.BytesIO(b"png-bytes"), "image/png")},
        )
        self.assertEqual(response.status_code, 403)

    def test_media_delete_is_store_scoped_and_soft_deleted(self):
        uploaded = self.client.post(
            "/api/v1/admin/media",
            headers=self._headers(self.manager_id),
            files={"file": ("cover.jpg", io.BytesIO(b"jpg-bytes"), "image/jpeg")},
        ).json()
        denied = self.client.delete(f"/api/v1/admin/media/{uploaded['id']}", headers=self._headers(self.other_manager_id))
        self.assertEqual(denied.status_code, 404)
        deleted = self.client.delete(f"/api/v1/admin/media/{uploaded['id']}", headers=self._headers(self.manager_id))
        self.assertEqual(deleted.status_code, 204)
        with self.SessionLocal() as db:
            media = db.get(__import__("app.models", fromlist=["MediaAsset"]).MediaAsset, uploaded["id"])
            self.assertIsNotNone(media)
            self.assertIsNotNone(media.deleted_at)

    def test_qiniu_backend_uses_storage_adapter_and_cdn_url(self):
        storage = _FakeStorage()
        with patch("app.api.media.get_media_storage", return_value=storage), patch.object(
            __import__("app.core.config", fromlist=["settings"]).settings,
            "media_storage_backend",
            "qiniu",
        ):
            response = self.client.post(
                "/api/v1/admin/media",
                headers=self._headers(self.manager_id),
                files={"file": ("cover.png", io.BytesIO(b"png-bytes"), "image/png")},
                data={"purpose": "project_cover"},
            )
            self.assertEqual(response.status_code, 201, response.text)
            body = response.json()
            self.assertEqual(body["url"], f"/api/v1/admin/media/{body['id']}/content")
            self.client.delete(f"/api/v1/admin/media/{body['id']}", headers=self._headers(self.manager_id))
        self.assertEqual(len(storage.put_calls), 1)
        self.assertEqual(storage.delete_calls, [storage.put_calls[0][0]])

    def test_storage_delete_failure_does_not_soft_delete_database_record(self):
        uploaded = self.client.post(
            "/api/v1/admin/media",
            headers=self._headers(self.manager_id),
            files={"file": ("cover.jpg", io.BytesIO(b"jpg-bytes"), "image/jpeg")},
        ).json()
        storage = _FailingDeleteStorage()
        with patch("app.api.media.get_media_storage", return_value=storage):
            response = self.client.delete(f"/api/v1/admin/media/{uploaded['id']}", headers=self._headers(self.manager_id))
        self.assertEqual(response.status_code, 502)
        with self.SessionLocal() as db:
            media = db.get(__import__("app.models", fromlist=["MediaAsset"]).MediaAsset, uploaded["id"])
            self.assertIsNone(media.deleted_at)


if __name__ == "__main__":
    unittest.main()
