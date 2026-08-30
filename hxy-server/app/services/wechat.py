"""微信小程序能力封装：登录 code2Session、手机号解析（预留）。"""

import httpx

from app.core.config import settings


async def code2session(code: str) -> dict:
    """用 wx.login 的 code 换取 openid + session_key。"""
    url = "https://api.weixin.qq.com/sns/jscode2session"
    params = {
        "appid": settings.wx_appid,
        "secret": settings.wx_appsecret,
        "js_code": code,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
        data = resp.json()
    if "openid" not in data:
        raise ValueError(f"code2Session 失败: {data.get('errcode')} {data.get('errmsg')}")
    return data
