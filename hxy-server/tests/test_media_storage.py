import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.core.config import Settings
from app.services.media_storage import MediaStorageError, QiniuMediaStorage


class _FakeAuth:
    instances = []

    def __init__(self, access_key, secret_key):
        self.access_key = access_key
        self.secret_key = secret_key
        self.upload_token_calls = []
        self.__class__.instances.append(self)

    def upload_token(self, bucket, key, expires=3600):
        self.upload_token_calls.append((bucket, key, expires))
        return "upload-token"


class _FakeBucketManager:
    instances = []

    def __init__(self, auth, config=None):
        self.auth = auth
        self.config = config
        self.delete_calls = []
        self.__class__.instances.append(self)

    def delete(self, bucket, key):
        self.delete_calls.append((bucket, key))
        return {}, SimpleNamespace(status_code=200)


class _FakeQiniu:
    Auth = _FakeAuth
    BucketManager = _FakeBucketManager

    @staticmethod
    def Config(**kwargs):
        return kwargs

    @staticmethod
    def put_data(token, key, data, **kwargs):
        _FakeQiniu.put_data_calls.append((token, key, data, kwargs))
        return {"key": key}, SimpleNamespace(status_code=200)


_FakeQiniu.put_data_calls = []


class MediaStorageTests(unittest.TestCase):
    def setUp(self):
        _FakeAuth.instances.clear()
        _FakeBucketManager.instances.clear()
        _FakeQiniu.put_data_calls.clear()

    def test_settings_read_qiniu_environment(self):
        env = {
            "MEDIA_STORAGE_BACKEND": "qiniu",
            "QINIU_ACCESS_KEY": "ak-test",
            "QINIU_SECRET_KEY": "sk-test",
            "QINIU_BUCKET": "diyhxy",
            "QINIU_CDN_DOMAIN": "https://img.hexiaoyue.com",
            "QINIU_ZONE": "z0",
        }
        with patch.dict(os.environ, env, clear=False):
            loaded = Settings(_env_file=None)
        self.assertEqual(loaded.media_storage_backend, "qiniu")
        self.assertEqual(loaded.qiniu_access_key, "ak-test")
        self.assertEqual(loaded.qiniu_secret_key, "sk-test")
        self.assertEqual(loaded.qiniu_bucket, "diyhxy")
        self.assertEqual(loaded.qiniu_cdn_domain, "https://img.hexiaoyue.com")
        self.assertEqual(loaded.qiniu_zone, "z0")

    def test_qiniu_put_data_uses_credentials_and_returns_cdn_url(self):
        storage = QiniuMediaStorage(
            access_key="ak-test",
            secret_key="sk-test",
            bucket="diyhxy",
            cdn_domain="https://img.hexiaoyue.com",
            qiniu_module=_FakeQiniu,
        )

        storage.put("stores/1/media/a.png", b"png", "image/png")

        self.assertEqual(_FakeAuth.instances[0].access_key, "ak-test")
        self.assertEqual(_FakeQiniu.put_data_calls[0][0], "upload-token")
        self.assertEqual(_FakeQiniu.put_data_calls[0][1], "stores/1/media/a.png")
        self.assertEqual(_FakeQiniu.put_data_calls[0][2], b"png")
        self.assertEqual(_FakeQiniu.put_data_calls[0][3]["mime_type"], "image/png")
        self.assertEqual(storage.url("stores/1/media/a.png"), "https://img.hexiaoyue.com/stores/1/media/a.png")

    def test_qiniu_delete_calls_bucket_manager(self):
        storage = QiniuMediaStorage(
            access_key="ak-test",
            secret_key="sk-test",
            bucket="diyhxy",
            cdn_domain="https://img.hexiaoyue.com",
            qiniu_module=_FakeQiniu,
        )

        storage.delete("stores/1/media/a.png")

        self.assertEqual(_FakeBucketManager.instances[0].delete_calls, [("diyhxy", "stores/1/media/a.png")])

    def test_qiniu_requires_all_credentials(self):
        with self.assertRaises(MediaStorageError):
            QiniuMediaStorage(
                access_key="",
                secret_key="sk-test",
                bucket="diyhxy",
                cdn_domain="https://img.hexiaoyue.com",
                qiniu_module=_FakeQiniu,
            )


if __name__ == "__main__":
    unittest.main()
