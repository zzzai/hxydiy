"""媒体对象存储适配器。

路由只依赖本文件的统一接口，避免把七牛 SDK 细节泄漏到 API 层。
"""

from pathlib import Path
import inspect
from typing import Protocol
from urllib.parse import quote


class MediaStorageError(RuntimeError):
    """媒体存储配置或远端操作失败。"""


class MediaStorage(Protocol):
    def put(self, object_key: str, content: bytes, content_type: str) -> None: ...

    def delete(self, object_key: str) -> None: ...

    def url(self, object_key: str) -> str | None: ...


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

    def delete(self, object_key: str) -> None:
        try:
            manager_params = inspect.signature(self.qiniu.BucketManager).parameters
            if self.zone is not None and "zone" in manager_params:
                manager = self.qiniu.BucketManager(self.auth, zone=self.zone)
            elif self.config is not None:
                manager = self.qiniu.BucketManager(self.auth, self.config)
            else:
                manager = self.qiniu.BucketManager(self.auth)
            _, info = manager.delete(self.bucket, object_key)
        except Exception as exc:
            raise MediaStorageError(f"七牛云删除失败: {exc}") from exc
        if getattr(info, "status_code", None) not in (200, 612):
            raise MediaStorageError(f"七牛云删除失败，HTTP {getattr(info, 'status_code', 'unknown')}")

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
