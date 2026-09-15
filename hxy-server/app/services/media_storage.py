"""媒体对象存储适配器。

路由只依赖本文件的统一接口，避免把七牛 SDK 细节泄漏到 API 层。
"""

from pathlib import Path
import inspect
from typing import Protocol
from urllib.parse import quote
from urllib.request import urlopen


class MediaStorageError(RuntimeError):
    """媒体存储配置或远端操作失败。"""


class MediaStorage(Protocol):
    def put(self, object_key: str, content: bytes, content_type: str) -> None: ...

    def delete(self, object_key: str) -> None: ...

    def url(self, object_key: str) -> str | None: ...


class DirectUploadStorage(MediaStorage, Protocol):
    def create_direct_upload_token(self, object_key: str, max_size_bytes: int, allowed_types: set[str]) -> str: ...

    def read(self, object_key: str, max_size_bytes: int) -> bytes: ...

    def move(self, source_key: str, destination_key: str) -> None: ...


class LocalMediaStorage:
    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def _path(self, object_key: str) -> Path:
        path = (self.root / object_key).resolve()
        if self.root != path and self.root not in path.parents:
            raise MediaStorageError("媒体存储路径配置无效")
        return path

    def put(self, object_key: str, content: bytes, content_type: str) -> None:
        del content_type
        path = self._path(object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def delete(self, object_key: str) -> None:
        path = self._path(object_key)
        try:
            path.unlink()
        except FileNotFoundError:
            # 幂等删除：对象已经不存在时，数据库仍可安全标记为已删除。
            return

    def url(self, object_key: str) -> str | None:
        del object_key
        return None

    def path(self, object_key: str) -> Path:
        return self._path(object_key)


class QiniuMediaStorage:
    def __init__(
        self,
        access_key: str,
        secret_key: str,
        bucket: str,
        cdn_domain: str,
        zone: str = "",
        signed_url_ttl_seconds: int = 600,
        qiniu_module=None,
    ):
        if not access_key or not secret_key:
            raise MediaStorageError("七牛云未配置 QINIU_ACCESS_KEY 或 QINIU_SECRET_KEY")
        if not bucket:
            raise MediaStorageError("七牛云未配置 QINIU_BUCKET")
        if not cdn_domain:
            raise MediaStorageError("七牛云未配置 QINIU_CDN_DOMAIN")
        try:
            self.qiniu = qiniu_module or __import__("qiniu")
        except ImportError as exc:
            raise MediaStorageError("七牛云 SDK 未安装，请安装 qiniu 依赖") from exc
        self.bucket = bucket
        self.cdn_domain = cdn_domain.rstrip("/")
        if not self.cdn_domain.startswith(("http://", "https://")):
            self.cdn_domain = f"https://{self.cdn_domain}"
        self.auth = self.qiniu.Auth(access_key, secret_key)
        if signed_url_ttl_seconds <= 0:
            raise MediaStorageError("七牛云签名 URL 有效期必须大于 0 秒")
        self.signed_url_ttl_seconds = signed_url_ttl_seconds
        # 新版 SDK 会按上传凭证自动查询区域；旧版 SDK 则可通过 Config/Zone 显式指定。
        self.zone = None
        if zone:
            zone_module = getattr(self.qiniu, "zone", None)
            self.zone = getattr(zone_module, f"Zone_{zone}", None) if zone_module else None
            if self.zone is None:
                self.zone = getattr(self.qiniu, f"Zone_{zone}", None)
        config_factory = getattr(self.qiniu, "Config", None)
        self.config = config_factory(use_https=self.cdn_domain.startswith("https://")) if config_factory else None

    def put(self, object_key: str, content: bytes, content_type: str) -> None:
        token = self.auth.upload_token(self.bucket, object_key, 3600)
        try:
            upload_kwargs = {"mime_type": content_type}
            if self.config is not None and "config" in inspect.signature(self.qiniu.put_data).parameters:
                upload_kwargs["config"] = self.config
            _, info = self.qiniu.put_data(token, object_key, content, **upload_kwargs)
        except Exception as exc:  # SDK 异常类型随版本变化，统一转换为业务错误。
            raise MediaStorageError(f"七牛云上传失败: {exc}") from exc
        if getattr(info, "status_code", None) != 200:
            raise MediaStorageError(f"七牛云上传失败，HTTP {getattr(info, 'status_code', 'unknown')}")

    def create_direct_upload_token(self, object_key: str, max_size_bytes: int, allowed_types: set[str]) -> str:
        policy = {
            "insertOnly": 1,
            "fsizeLimit": max_size_bytes,
            "detectMime": 1,
            "mimeLimit": ";".join(sorted(allowed_types)),
        }
        try:
            return self.auth.upload_token(self.bucket, object_key, 3600, policy=policy)
        except Exception as exc:
            raise MediaStorageError(f"七牛云生成上传凭证失败: {exc}") from exc

    def _bucket_manager(self):
        try:
            manager_params = inspect.signature(self.qiniu.BucketManager).parameters
            if self.zone is not None and "zone" in manager_params:
                return self.qiniu.BucketManager(self.auth, zone=self.zone)
            if self.config is not None:
                return self.qiniu.BucketManager(self.auth, self.config)
            return self.qiniu.BucketManager(self.auth)
        except Exception as exc:
            raise MediaStorageError(f"七牛云初始化对象管理器失败: {exc}") from exc

    def delete(self, object_key: str) -> None:
        try:
            manager = self._bucket_manager()
            _, info = manager.delete(self.bucket, object_key)
        except Exception as exc:
            raise MediaStorageError(f"七牛云删除失败: {exc}") from exc
        if getattr(info, "status_code", None) not in (200, 612):
            raise MediaStorageError(f"七牛云删除失败，HTTP {getattr(info, 'status_code', 'unknown')}")

    def read(self, object_key: str, max_size_bytes: int) -> bytes:
        try:
            with urlopen(self.url(object_key), timeout=15) as response:
                content = response.read(max_size_bytes + 1)
        except Exception as exc:
            raise MediaStorageError(f"七牛云读取对象失败: {exc}") from exc
        if len(content) > max_size_bytes:
            raise MediaStorageError("七牛云对象超过允许大小")
        return content

    def move(self, source_key: str, destination_key: str) -> None:
        try:
            _, info = self._bucket_manager().move(self.bucket, source_key, self.bucket, destination_key, force="false")
        except Exception as exc:
            raise MediaStorageError(f"七牛云移动对象失败: {exc}") from exc
        if getattr(info, "status_code", None) != 200:
            raise MediaStorageError(f"七牛云移动对象失败，HTTP {getattr(info, 'status_code', 'unknown')}")

    def url(self, object_key: str) -> str:
        public_url = f"{self.cdn_domain}/{quote(object_key, safe='/')}"
        # 生产空间通常禁止匿名访问，优先返回短期签名 URL；fake/旧 SDK 无此能力时保留裸 URL 兼容性。
        private_download_url = getattr(self.auth, "private_download_url", None)
        if private_download_url is None:
            return public_url
        try:
            return private_download_url(public_url, expires=self.signed_url_ttl_seconds)
        except Exception as exc:
            raise MediaStorageError(f"七牛云生成签名 URL 失败: {exc}") from exc


def get_media_storage(runtime_settings) -> MediaStorage:
    backend = runtime_settings.media_storage_backend.strip().lower()
    if backend == "local":
        return LocalMediaStorage(runtime_settings.media_storage_root)
    if backend == "qiniu":
        return QiniuMediaStorage(
            access_key=runtime_settings.qiniu_access_key,
            secret_key=runtime_settings.qiniu_secret_key,
            bucket=runtime_settings.qiniu_bucket,
            cdn_domain=runtime_settings.qiniu_cdn_domain,
            zone=runtime_settings.qiniu_zone,
            signed_url_ttl_seconds=runtime_settings.qiniu_signed_url_ttl_seconds,
        )
    raise MediaStorageError(f"不支持的媒体存储后端: {runtime_settings.media_storage_backend}")
