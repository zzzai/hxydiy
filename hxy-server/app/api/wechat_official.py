"""Public endpoints needed by the certified WeChat service account H5."""

from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.services.wechat_official import OfficialWechatError, official_wechat_jssdk


router = APIRouter(tags=["wechat"])


def _is_public_h5_url(value: str) -> bool:
    expected = urlsplit(settings.h5_public_base_url)
    actual = urlsplit(value)
    root_path = expected.path.rstrip("/") or "/"
    return (
        actual.scheme == expected.scheme
        and actual.netloc == expected.netloc
        and actual.path.startswith(root_path)
        and not actual.fragment
    )


@router.get("/api/v1/wechat/jssdk-config")
async def jssdk_config(url: str = Query(..., min_length=1)) -> dict[str, str | int]:
    """Sign only URLs served by this H5, never arbitrary third-party URLs."""
    if not _is_public_h5_url(url):
        raise HTTPException(status_code=422, detail="仅支持荷小悦顾客端页面")
    if not settings.wechat_official_enabled:
        raise HTTPException(status_code=503, detail="认证服务号尚未配置")
    try:
        return await official_wechat_jssdk.config_for_url(url)
    except OfficialWechatError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
