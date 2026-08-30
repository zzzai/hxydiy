"""管理端媒体上传与门店隔离访问。"""

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.admin import _current_staff, normalize_staff_role
from app.api.admin_v2 import _audit, _is_headquarters_admin, _staff_store_id
from app.core.config import settings
from app.db.session import get_db
from app.models import MediaAsset, Staff, Store

router = APIRouter(prefix="/admin/media", tags=["admin-media"])

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}


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


def _view(media: MediaAsset) -> dict:
    return {
        "id": media.id,
        "store_id": media.store_id,
        "original_name": media.original_name,
        "content_type": media.content_type,
        "media_type": media.media_type,
        "size_bytes": media.size_bytes,
        "purpose": media.purpose,
        "url": f"/api/v1/admin/media/{media.id}/content",
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
    if settings.environment == "production" and settings.media_storage_backend != "oss":
        raise HTTPException(status_code=503, detail="生产媒体存储尚未配置 OSS")
    if not db.get(Store, target_store_id):
        raise HTTPException(status_code=404, detail="门店不存在")
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="仅支持 JPG、PNG、WebP 或 GIF 图片")
    original_name = Path(file.filename or "upload").name
    if not original_name or len(original_name) > 255:
        raise HTTPException(status_code=400, detail="文件名无效")
    content = await file.read(settings.media_max_size_bytes + 1)
    if len(content) > settings.media_max_size_bytes:
        raise HTTPException(status_code=413, detail="图片不能超过 5MB")
    object_key = f"stores/{target_store_id}/media/{uuid4().hex}{EXTENSIONS[file.content_type]}"
    root = Path(settings.media_storage_root).resolve()
    target = (root / object_key).resolve()
    if root not in target.parents:
        raise HTTPException(status_code=500, detail="媒体存储路径配置无效")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
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
    return _view(media)


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
    query = select(MediaAsset).where(MediaAsset.store_id == target_store_id, MediaAsset.deleted_at.is_(None)).order_by(MediaAsset.id.desc())
    if purpose:
        query = query.where(MediaAsset.purpose == purpose)
    items = list(db.scalars(query))
    return {"items": [_view(item) for item in items], "total": len(items)}


@router.get("/{media_id}/content")
def get_media_content(media_id: int, db: Session = Depends(get_db), authorization: str | None = Header(None)):
    staff = _current_staff(authorization, db)
    media = db.get(MediaAsset, media_id)
    if not media or media.deleted_at or (not _is_headquarters_admin(staff) and media.store_id != _media_store_id(staff, None)):
        raise HTTPException(status_code=404, detail="媒体不存在")
    path = (Path(settings.media_storage_root).resolve() / media.object_key).resolve()
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
    media.deleted_at = datetime.now(timezone.utc)
    _audit(db, staff, "media_delete", "media", str(media.id), {"store_id": media.store_id})
    db.commit()
