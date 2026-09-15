import io
import struct
import unittest
import zlib
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import AuditLog, MediaAsset, PageContent, Project, Staff, Store
from app.services.media_storage import MediaStorageError


def _png(width: int, height: int) -> bytes:
    def chunk(kind: bytes, value: bytes) -> bytes:
        return struct.pack(">I", len(value)) + kind + value + struct.pack(">I", zlib.crc32(kind + value) & 0xFFFFFFFF)

    row = b"\x00" + b"\x00\x00\x00" * width
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(row * height)) + chunk(b"IEND", b"")


PNG_1X1 = _png(1, 1)
PNG_2X1 = _png(2, 1)


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


class _DirectUploadStorage(_FakeStorage):
    def __init__(self):
        super().__init__()
        self.direct_upload_token_calls = []
        self.objects = {}
        self.move_calls = []

    def create_direct_upload_token(self, object_key, max_size_bytes, allowed_types):
        self.direct_upload_token_calls.append((object_key, max_size_bytes, allowed_types))
        return "qiniu-direct-upload-token"

    def read(self, object_key, max_size_bytes):
        content = self.objects[object_key]
        if len(content) > max_size_bytes:
            raise MediaStorageError("对象超过允许大小")
        return content

    def move(self, source_key, destination_key):
        self.move_calls.append((source_key, destination_key))
        self.objects[destination_key] = self.objects.pop(source_key)


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
            files={"file": ("cover.png", io.BytesIO(PNG_1X1), "image/png")},
            data={"purpose": "project_cover"},
        )
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["media_type"], "image")
        self.assertEqual(body["original_name"], "cover.png")
        self.assertEqual(body["purpose"], "project_cover")
        self.assertTrue(body["url"].startswith("/api/v1/admin/media/"))
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

    def test_upload_rejects_non_image_bytes_declared_as_png_before_storage_write(self):
        storage = _FakeStorage()
        with patch("app.api.media.get_media_storage", return_value=storage):
            response = self.client.post(
                "/api/v1/admin/media",
                headers=self._headers(self.manager_id),
                files={"file": ("cover.png", io.BytesIO(b"not-an-image"), "image/png")},
            )
        self.assertEqual(response.status_code, 415, response.text)
        self.assertEqual(storage.put_calls, [])

    def test_upload_rejects_extension_that_disagrees_with_declared_image_type(self):
        storage = _FakeStorage()
        with patch("app.api.media.get_media_storage", return_value=storage):
            response = self.client.post(
                "/api/v1/admin/media",
                headers=self._headers(self.manager_id),
                files={"file": ("cover.jpg", io.BytesIO(PNG_1X1), "image/png")},
            )
        self.assertEqual(response.status_code, 415, response.text)
        self.assertEqual(storage.put_calls, [])

    def test_upload_rejects_image_over_configured_pixel_limit_before_storage_write(self):
        storage = _FakeStorage()
        media_settings = __import__("app.core.config", fromlist=["settings"]).settings
        with patch("app.api.media.get_media_storage", return_value=storage), patch.object(
            media_settings,
            "media_max_pixels",
            1,
        ):
            response = self.client.post(
                "/api/v1/admin/media",
                headers=self._headers(self.manager_id),
                files={"file": ("cover.png", io.BytesIO(PNG_2X1), "image/png")},
            )
        self.assertEqual(response.status_code, 413, response.text)
        self.assertEqual(storage.put_calls, [])

    def test_regular_staff_cannot_upload_media(self):
        with self.SessionLocal() as db:
            staff = Staff(username="media-staff", password_hash=hash_password("pass"), name="员工", role="staff", store_id=1, status="active")
            db.add(staff)
            db.commit()
            staff_id = staff.id
        response = self.client.post(
            "/api/v1/admin/media",
            headers=self._headers(staff_id, "staff"),
            files={"file": ("cover.png", io.BytesIO(PNG_1X1), "image/png")},
        )
        self.assertEqual(response.status_code, 403)

    def test_media_delete_is_store_scoped_and_soft_deleted(self):
        uploaded = self.client.post(
            "/api/v1/admin/media",
            headers=self._headers(self.manager_id),
            files={"file": ("cover.png", io.BytesIO(PNG_1X1), "image/png")},
        ).json()
        denied = self.client.delete(f"/api/v1/admin/media/{uploaded['id']}", headers=self._headers(self.other_manager_id))
        self.assertEqual(denied.status_code, 404)
        deleted = self.client.delete(f"/api/v1/admin/media/{uploaded['id']}", headers=self._headers(self.manager_id))
        self.assertEqual(deleted.status_code, 204)
        with self.SessionLocal() as db:
            media = db.get(__import__("app.models", fromlist=["MediaAsset"]).MediaAsset, uploaded["id"])
            self.assertIsNotNone(media)
            self.assertIsNotNone(media.deleted_at)

    def test_media_delete_rejects_catalog_and_page_content_references(self):
        uploaded = self.client.post(
            "/api/v1/admin/media",
            headers=self._headers(self.manager_id),
            files={"file": ("cover.png", io.BytesIO(PNG_1X1), "image/png")},
        ).json()
        with self.SessionLocal() as db:
            db.add(Project(
                store_id=1,
                code="media-reference-project",
                category="bath",
                name="引用媒体项目",
                image_url=uploaded["url"],
                detail_modules=[{"type": "image", "body": uploaded["url"]}],
            ))
            db.add(PageContent(
                store_id=1,
                page_key="media-reference-page",
                promo_banners=[{"image": uploaded["url"]}],
            ))
            db.commit()

        response = self.client.delete(f"/api/v1/admin/media/{uploaded['id']}", headers=self._headers(self.manager_id))

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "MEDIA_IN_USE")
        self.assertEqual(response.json()["detail"]["reference_count"], 2)
        with self.SessionLocal() as db:
            self.assertIsNone(db.get(MediaAsset, uploaded["id"]).deleted_at)

    def test_media_delete_rejects_historical_signed_url_reference_by_object_key(self):
        storage = _FakeStorage()
        with patch("app.api.media.get_media_storage", return_value=storage):
            uploaded = self.client.post(
                "/api/v1/admin/media",
                headers=self._headers(self.manager_id),
                files={"file": ("cover.png", io.BytesIO(PNG_1X1), "image/png")},
            ).json()
        with self.SessionLocal() as db:
            db.add(Project(
                store_id=1,
                code="media-signed-url-project",
                category="bath",
                name="签名地址引用项目",
                image_url=f"{uploaded['url']}?e=expired-signature",
            ))
            db.commit()

        response = self.client.delete(f"/api/v1/admin/media/{uploaded['id']}", headers=self._headers(self.manager_id))

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "MEDIA_IN_USE")
        self.assertEqual(storage.delete_calls, [])
        with self.SessionLocal() as db:
            self.assertIsNone(db.get(MediaAsset, uploaded["id"]).deleted_at)

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
                files={"file": ("cover.png", io.BytesIO(PNG_1X1), "image/png")},
                data={"purpose": "project_cover"},
            )
            self.assertEqual(response.status_code, 201, response.text)
            body = response.json()
            self.assertEqual(body["url"], f"https://img.hexiaoyue.com/{storage.put_calls[0][0]}")
            self.client.delete(f"/api/v1/admin/media/{body['id']}", headers=self._headers(self.manager_id))
        self.assertEqual(len(storage.put_calls), 1)
        self.assertEqual(storage.delete_calls, [storage.put_calls[0][0]])

    def test_direct_upload_completion_creates_one_scoped_media_record_after_content_validation(self):
        storage = _DirectUploadStorage()
        media_settings = __import__("app.core.config", fromlist=["settings"]).settings
        with patch("app.api.media.get_media_storage", return_value=storage), patch.object(
            media_settings,
            "media_storage_backend",
            "qiniu",
        ):
            grant = self.client.post(
                "/api/v1/admin/media/direct-upload",
                headers=self._headers(self.manager_id),
                json={
                    "filename": "cover.png",
                    "content_type": "image/png",
                    "size_bytes": len(PNG_1X1),
                    "purpose": "project_cover",
                },
            )
            self.assertEqual(grant.status_code, 201, grant.text)
            grant_body = grant.json()
            self.assertEqual(grant_body["upload_token"], "qiniu-direct-upload-token")
            self.assertTrue(grant_body["key"].startswith("stores/1/media/staging/"))
            storage.objects[grant_body["key"]] = PNG_1X1

            completed = self.client.post(
                "/api/v1/admin/media/direct-upload/complete",
                headers=self._headers(self.manager_id),
                json={"ticket": grant_body["ticket"]},
            )
            self.assertEqual(completed.status_code, 201, completed.text)
            media = completed.json()
            self.assertEqual(media["original_name"], "cover.png")
            self.assertEqual(media["purpose"], "project_cover")
            self.assertTrue(storage.move_calls[0][0].startswith("stores/1/media/staging/"))
            self.assertTrue(storage.move_calls[0][1].startswith("stores/1/media/"))
            self.assertNotIn("/staging/", storage.move_calls[0][1])

            repeated = self.client.post(
                "/api/v1/admin/media/direct-upload/complete",
                headers=self._headers(self.manager_id),
                json={"ticket": grant_body["ticket"]},
            )
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertEqual(repeated.json()["id"], media["id"])
        with self.SessionLocal() as db:
            self.assertEqual(db.scalar(select(MediaAsset).where(MediaAsset.id == media["id"])).store_id, 1)

    def test_direct_upload_completion_rejects_another_store_manager_and_removes_invalid_object(self):
        storage = _DirectUploadStorage()
        media_settings = __import__("app.core.config", fromlist=["settings"]).settings
        with patch("app.api.media.get_media_storage", return_value=storage), patch.object(
            media_settings,
            "media_storage_backend",
            "qiniu",
        ):
            grant_response = self.client.post(
                "/api/v1/admin/media/direct-upload",
                headers=self._headers(self.manager_id),
                json={"filename": "invalid-direct.png", "content_type": "image/png", "size_bytes": len(PNG_1X1)},
            )
            self.assertEqual(grant_response.status_code, 201, grant_response.text)
            grant = grant_response.json()
            cross_store = self.client.post(
                "/api/v1/admin/media/direct-upload/complete",
                headers=self._headers(self.other_manager_id),
                json={"ticket": grant["ticket"]},
            )
            self.assertEqual(cross_store.status_code, 403, cross_store.text)

            storage.objects[grant["key"]] = b"x" * len(PNG_1X1)
            invalid = self.client.post(
                "/api/v1/admin/media/direct-upload/complete",
                headers=self._headers(self.manager_id),
                json={"ticket": grant["ticket"]},
            )
        self.assertEqual(invalid.status_code, 415, invalid.text)
        self.assertEqual(storage.delete_calls, [grant["key"]])
        with self.SessionLocal() as db:
            self.assertIsNone(db.scalar(select(MediaAsset).where(MediaAsset.original_name == "invalid-direct.png")))

    def test_storage_delete_failure_does_not_soft_delete_database_record(self):
        uploaded = self.client.post(
            "/api/v1/admin/media",
            headers=self._headers(self.manager_id),
            files={"file": ("cover.png", io.BytesIO(PNG_1X1), "image/png")},
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
