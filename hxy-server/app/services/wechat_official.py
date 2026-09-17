"""微信认证服务号网页 JS-SDK 签名。"""

from __future__ import annotations

from hashlib import sha1
from secrets import token_urlsafe
from time import time

import httpx

from app.core.config import settings


class OfficialWechatError(RuntimeError):
    """The public account credentials or WeChat upstream response are unavailable."""


class OfficialWechatJssdk:
    def __init__(self) -> None:
        self._access_token: tuple[str, float] | None = None
        self._jsapi_ticket: tuple[str, float] | None = None

    @staticmethod
    def _cached_value(value: tuple[str, float] | None) -> str | None:
        if value and value[1] > time():
            return value[0]
        return None

    @staticmethod
    async def _wechat_get(url: str, params: dict[str, str]) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise OfficialWechatError("微信服务返回格式异常")
        if payload.get("errcode"):
            raise OfficialWechatError("微信服务暂不可用")
        return payload

    @staticmethod
    def _expiry(payload: dict) -> float:
        expires_in = payload.get("expires_in")
        if not isinstance(expires_in, int) or expires_in <= 300:
            raise OfficialWechatError("微信服务未返回有效期限")
        return time() + expires_in - 300

    async def _get_access_token(self) -> str:
        cached = self._cached_value(self._access_token)
        if cached:
            return cached
        if not settings.wechat_official_enabled:
            raise OfficialWechatError("认证服务号尚未配置")
        payload = await self._wechat_get(
            "https://api.weixin.qq.com/cgi-bin/token",
            {
                "grant_type": "client_credential",
                "appid": settings.wechat_official_appid,
                "secret": settings.wechat_official_appsecret,
            },
        )
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise OfficialWechatError("微信服务未返回访问令牌")
        self._access_token = (token, self._expiry(payload))
        return token

    async def _get_jsapi_ticket(self) -> str:
        cached = self._cached_value(self._jsapi_ticket)
        if cached:
            return cached
        token = await self._get_access_token()
        payload = await self._wechat_get(
            "https://api.weixin.qq.com/cgi-bin/ticket/getticket",
            {"access_token": token, "type": "jsapi"},
        )
        ticket = payload.get("ticket")
        if not isinstance(ticket, str) or not ticket:
            raise OfficialWechatError("微信服务未返回网页授权票据")
        self._jsapi_ticket = (ticket, self._expiry(payload))
        return ticket

    async def config_for_url(self, url: str) -> dict[str, str | int]:
        ticket = await self._get_jsapi_ticket()
        timestamp = int(time())
        nonce = token_urlsafe(18)
        raw = f"jsapi_ticket={ticket}&noncestr={nonce}&timestamp={timestamp}&url={url}"
        return {
            "appId": settings.wechat_official_appid,
            "timestamp": timestamp,
            "nonceStr": nonce,
            "signature": sha1(raw.encode("utf-8")).hexdigest(),
        }


official_wechat_jssdk = OfficialWechatJssdk()
