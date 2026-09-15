"""管理端媒体上传与门店隔离访问。"""

from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from jose import JWTError, jwt
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.admin import _current_staff, normalize_staff_role
from app.api.admin_v2 import _audit, _staff_store_id
from app.core.config import settings
from app.db.session import get_db
from app.models import Addon, MediaAsset, PageContent, Product, Project, Staff, Store
from app.services.media_storage import MediaStorageError, get_media_storage as _build_media_storage

router = APIRouter(prefix="/admin/media", tags=["admin-media"])


def _is_headquarters_admin(staff: Staff) -> bool:
    """总部管理员是未绑定门店的 admin；兼容旧生产 admin_v2 helper 集合。"""
    return getattr(staff, "role", None) == "admin" and getattr(staff, "store_id", None) is None

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
FILENAME_EXTENSIONS = {"image/jpeg": {".jpg", ".jpeg"}, "image/png": {".png"}, "image/webp": {".webp"}, "image/gif": {".gif"}}
FORMAT_CONTENT_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "GIF": "image/gif"}
DIRECT_UPLOAD_TTL_SECONDS = 3600


class DirectUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str
    size_bytes: int = Field(gt=0)
    purpose: str = Field(default="general", min_length=1, max_length=32)
    store_id: int | None = None


class DirectUploadCompleteRequest(BaseModel):
    ticket: str = Field(min_length=1)


def _validate_image_content(content: bytes, declared_type: str) -> None:
    """Reject invalid, misdeclared, and oversized-pixel image data before storage."""

    try:
        with Image.open(BytesIO(content)) as image:
            actual_type = FORMAT_CONTENT_TYPES.get(image.format or "")
            if actual_type != declared_type:
                raise HTTPException(status_code=415, detail="图片内容与声明类型不一致")
            if image.width * image.height > settings.media_max_pixels:
                raise HTTPException(status_code=413, detail="图片像素不能超过 2500 万")
            image.verify()
    except HTTPException:
        raise
    except (Image.DecompressionBombError, OSError, UnidentifiedImageError, ValueError) as exc:
        raise HTTPException(status_code=415, detail="图片内容无效") from exc


def _validate_image_metadata(filename: str, content_type: str, size_bytes: int) -> str:
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="仅支持 JPG、PNG、WebP 或 GIF 图片")
    original_name = Path(filename).name
    if not original_name or len(original_name) > 255:
        raise HTTPException(status_code=400, detail="文件名无效")
    if Path(original_name).suffix.lower() not in FILENAME_EXTENSIONS[content_type]:
        raise HTTPException(status_code=415, detail="文件扩展名与图片类型不一致")
    if size_bytes > settings.media_max_size_bytes:
        raise HTTPException(status_code=413, detail="图片不能超过 5MB")
    return original_name


def _value_references_media(value: object, reference_values: tuple[str, ...]) -> bool:
    """Return whether a catalog or page-content value still refers to media."""

    if isinstance(value, str):
        return any(reference in value for reference in reference_values)
    if isinstance(value, dict):
        return any(_value_references_media(item, reference_values) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_value_references_media(item, reference_values) for item in value)
    return False


def _media_references(db: Session, media: MediaAsset) -> list[dict[str, int | str]]:
    """Find same-store catalog/page-content records that still use a media object.

    The object key catches historical signed CDN URLs, while the controlled path
    catches local-storage URLs. Do not expose the referenced content itself in
    the deletion response.
    """

    reference_values = (media.object_key, f"/api/v1/admin/media/{media.id}/content")
    references: list[dict[str, int | str]] = []
    candidates = (
        (Project, "project", ("image_url", "detail_modules")),
        (Addon, "addon", ("image_url",)),
        (Product, "product", ("image_url",)),
        (PageContent, "page_content", ("promo_banners", "tea_options", "coupon_prompt", "brand_story")),
    )
    for model, resource_type, fields in candidates:
        for record in db.scalars(select(model).where(model.store_id == media.store_id)):
            if any(_value_references_media(getattr(record, field), reference_values) for field in fields):
                references.append({"resource_type": resource_type, "resource_id": record.id})
    return references


def _require_media_writer(staff: Staff) -> None:
    if _is_headquarters_admin(staff):
        return
    try:
        role = normalize_staff_role(staff.role, staff.technician_id)
    except (AttributeError, ValueError, TypeError):
        role = None
    if role != "manager":
        raise HTTPException(status_code=403, detail={"code": "MANAGER_REQUIRED", "message": "仅管理员或店长可以管理媒体"})


def _media_store_id(staff: Staff, requested: int | None) -> int:
    if _is_headquarters_admin(staff):
        if requested is None:
            raise HTTPException(status_code=400, detail="总部上传必须指定门店")
        return requested
    store_id = _staff_store_id(staff)
    if requested is not None and requested != store_id:
        raise HTTPException(status_code=403, detail="无权访问其他门店数据")
    return store_id


def get_media_storage():
    """按当前运行配置创建存储适配器；测试可替换此工厂。"""

    return _build_media_storage(settings)


def _storage_or_http():
    try:
        return get_media_storage()
    except MediaStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _direct_storage_or_http():
    if settings.media_storage_backend.strip().lower() != "qiniu":
        raise HTTPException(
            status_code=409,
            detail={"code": "DIRECT_UPLOAD_UNAVAILABLE", "message": "当前环境未启用七牛直传"},
        )
    storage = _storage_or_http()
    required_methods = ("create_direct_upload_token", "read", "move")
    if not all(callable(getattr(storage, method, None)) for method in required_methods):
        raise HTTPException(status_code=503, detail="当前七牛存储不支持直传")
    return storage


def _create_direct_upload_ticket(staff: Staff, store_id: int, request: DirectUploadRequest, staging_key: str, final_key: str) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=DIRECT_UPLOAD_TTL_SECONDS)
    return jwt.encode(
        {
            "token_type": "media_direct_upload",
            "sub": str(staff.id),
            "store_id": store_id,
            "original_name": Path(request.filename).name,
            "content_type": request.content_type,
            "size_bytes": request.size_bytes,
            "purpose": request.purpose,
            "staging_key": staging_key,
            "final_key": final_key,
            "exp": expires_at,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def _decode_direct_upload_ticket(ticket: str, staff: Staff) -> dict:
    try:
        payload = jwt.decode(ticket, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(status_code=400, detail="上传凭证无效或已过期") from exc
    if payload.get("token_type") != "media_direct_upload":
        raise HTTPException(status_code=400, detail="上传凭证类型无效")
    if payload.get("sub") != str(staff.id):
        raise HTTPException(status_code=403, detail="无权完成其他员工的上传")
    return payload


def _view(media: MediaAsset, storage=None) -> dict:
    public_url = storage.url(media.object_key) if storage else None
    return {
        "id": media.id,
        "store_id": media.store_id,
        "original_name": media.original_name,
        "content_type": media.content_type,
        "media_type": media.media_type,
        "size_bytes": media.size_bytes,
        "purpose": media.purpose,
        "url": public_url or f"/api/v1/admin/media/{media.id}/content",
        "created_at": media.created_at.isoformat() if media.created_at else None,
    }


@router.post("", status_code=201)
async def upload_media(
    file: UploadFile,
    purpose: str = Form("general", min_length=1, max_length=32),
    store_id: int | None = Form(None),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    _require_media_writer(staff)
    target_store_id = _media_store_id(staff, store_id)
    if settings.environment == "production" and settings.media_storage_backend.strip().lower() != "qiniu":
        raise HTTPException(status_code=503, detail="生产媒体存储必须配置七牛云")
    if not db.get(Store, target_store_id):
        raise HTTPException(status_code=404, detail="门店不存在")
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="仅支持 JPG、PNG、WebP 或 GIF 图片")
    original_name = Path(file.filename or "upload").name
    if not original_name or len(original_name) > 255:
        raise HTTPException(status_code=400, detail="文件名无效")
    if Path(original_name).suffix.lower() not in FILENAME_EXTENSIONS[file.content_type]:
        raise HTTPException(status_code=415, detail="文件扩展名与图片类型不一致")
    content = await file.read(settings.media_max_size_bytes + 1)
    if len(content) > settings.media_max_size_bytes:
        raise HTTPException(status_code=413, detail="图片不能超过 5MB")
    _validate_image_content(content, file.content_type)
    object_key = f"stores/{target_store_id}/media/{uuid4().hex}{EXTENSIONS[file.content_type]}"
    storage = _storage_or_http()
    try:
        storage.put(object_key, content, file.content_type)
    except MediaStorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    media = MediaAsset(
        store_id=target_store_id,
        object_key=object_key,
        original_name=original_name,
        content_type=file.content_type,
        media_type="image",
        size_bytes=len(content),
        purpose=purpose,
        created_by_staff_id=staff.id,
    )
    db.add(media)
    db.flush()
    _audit(db, staff, "media_upload", "media", str(media.id), {"store_id": target_store_id, "purpose": purpose, "size_bytes": len(content)})
    db.commit()
    db.refresh(media)
    return _view(media, storage)


@router.post("/direct-upload", status_code=201)
def create_direct_upload(
    request: DirectUploadRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    _require_media_writer(staff)
    target_store_id = _media_store_id(staff, request.store_id)
    if not db.get(Store, target_store_id):
        raise HTTPException(status_code=404, detail="门店不存在")
    original_name = _validate_image_metadata(request.filename, request.content_type, request.size_bytes)
    storage = _direct_storage_or_http()
    object_id = uuid4().hex
    extension = EXTENSIONS[request.content_type]
    staging_key = f"stores/{target_store_id}/media/staging/{object_id}{extension}"
    final_key = f"stores/{target_store_id}/media/{object_id}{extension}"
    try:
        upload_token = storage.create_direct_upload_token(staging_key, settings.media_max_size_bytes, ALLOWED_TYPES)
    except MediaStorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    ticket = _create_direct_upload_ticket(staff, target_store_id, request, staging_key, final_key)
    _audit(
        db,
        staff,
        "media_direct_upload_issued",
        "media_upload",
        staging_key,
        {"store_id": target_store_id, "purpose": request.purpose, "size_bytes": request.size_bytes},
    )
    db.commit()
    return {"upload_token": upload_token, "key": staging_key, "ticket": ticket}


@router.post("/direct-upload/complete", status_code=201)
def complete_direct_upload(
    request: DirectUploadCompleteRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    _require_media_writer(staff)
    ticket = _decode_direct_upload_ticket(request.ticket, staff)
    target_store_id = _media_store_id(staff, int(ticket["store_id"]))
    original_name = _validate_image_metadata(ticket["original_name"], ticket["content_type"], int(ticket["size_bytes"]))
    storage = _direct_storage_or_http()
    existing = db.scalar(select(MediaAsset).where(MediaAsset.object_key == ticket["final_key"]))
    if existing:
        return JSONResponse(_view(existing, storage), status_code=200)
    try:
        content = storage.read(ticket["staging_key"], settings.media_max_size_bytes)
        if len(content) != int(ticket["size_bytes"]):
            raise HTTPException(status_code=400, detail="图片大小与上传凭证不一致")
        _validate_image_content(content, ticket["content_type"])
        storage.move(ticket["staging_key"], ticket["final_key"])
    except HTTPException:
        try:
            storage.delete(ticket["staging_key"])
        except MediaStorageError:
            pass
        raise
    except MediaStorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    media = MediaAsset(
        store_id=target_store_id,
        object_key=ticket["final_key"],
        original_name=original_name,
        content_type=ticket["content_type"],
        media_type="image",
        size_bytes=len(content),
        purpose=ticket["purpose"],
        created_by_staff_id=staff.id,
    )
    db.add(media)
    db.flush()
    _audit(
        db,
        staff,
        "media_direct_upload",
        "media",
        str(media.id),
        {"store_id": target_store_id, "purpose": media.purpose, "size_bytes": media.size_bytes},
    )
    db.commit()
    db.refresh(media)
    return _view(media, storage)


@router.get("")
def list_media(
    purpose: str | None = Query(None),
    store_id: int | None = Query(None),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    staff = _current_staff(authorization, db)
    _require_media_writer(staff)
    target_store_id = _media_store_id(staff, store_id)
    storage = _storage_or_http()
    query = select(MediaAsset).where(MediaAsset.store_id == target_store_id, MediaAsset.deleted_at.is_(None)).order_by(MediaAsset.id.desc())
    if purpose:
        query = query.where(MediaAsset.purpose == purpose)
    items = list(db.scalars(query))
    return {"items": [_view(item, storage) for item in items], "total": len(items)}


@router.get("/{media_id}/content")
def get_media_content(media_id: int, db: Session = Depends(get_db), authorization: str | None = Header(None)):
    staff = _current_staff(authorization, db)
    media = db.get(MediaAsset, media_id)
    if not media or media.deleted_at or (not _is_headquarters_admin(staff) and media.store_id != _media_store_id(staff, None)):
        raise HTTPException(status_code=404, detail="媒体不存在")
    storage = _storage_or_http()
    public_url = storage.url(media.object_key)
    if public_url:
        return RedirectResponse(public_url, status_code=307)
    if not hasattr(storage, "path"):
        raise HTTPException(status_code=503, detail="当前媒体存储不支持内容代理")
    path = storage.path(media.object_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="媒体文件不存在")
    return FileResponse(path, media_type=media.content_type, filename=media.original_name)


@router.delete("/{media_id}", status_code=204)
def delete_media(media_id: int, db: Session = Depends(get_db), authorization: str | None = Header(None)):
    staff = _current_staff(authorization, db)
    _require_media_writer(staff)
    media = db.get(MediaAsset, media_id)
    if not media or media.deleted_at or (not _is_headquarters_admin(staff) and media.store_id != _media_store_id(staff, None)):
        raise HTTPException(status_code=404, detail="媒体不存在")
    references = _media_references(db, media)
    if references:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MEDIA_IN_USE",
                "message": "媒体仍被内容引用，请先解除引用后再删除",
                "reference_count": len(references),
            },
        )
    storage = _storage_or_http()
    try:
        storage.delete(media.object_key)
    except MediaStorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    media.deleted_at = datetime.now(timezone.utc)
    _audit(db, staff, "media_delete", "media", str(media.id), {"store_id": media.store_id})
    db.commit()
