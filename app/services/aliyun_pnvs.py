"""阿里云号码认证服务（短信认证）封装。

短信认证走 SendSmsVerifyCode / CheckSmsVerifyCode：
- 发送时由阿里云生成验证码（template_param 用 "##code##"），后端不落库验证码明文；
- 校验时调用阿里云核验手机号与验证码是否匹配。
SDK 未安装时 _get_client 返回 None，由调用方按“未启用”处理。
"""

from app.core.config import settings


class AliyunPnvsError(Exception):
    """阿里云短信认证服务异常（网络/配置/业务失败），应映射为 502。"""


_client = None


def _get_client():
    global _client
    if _client is None:
        try:
            from alibabacloud_dypnsapi20170525.client import Client
            from alibabacloud_tea_openapi import models as open_api_models
        except ImportError:
            return None
        config = open_api_models.Config(
            access_key_id=settings.aliyun_pnvs_access_key_id,
            access_key_secret=settings.aliyun_pnvs_access_key_secret,
        )
        config.endpoint = "dypnsapi.aliyuncs.com"
        _client = Client(config)
    return _client


def _send_request(phone: str):
    from alibabacloud_dypnsapi20170525 import models as dypnsapi_models
    from alibabacloud_tea_util import models as util_models

    return dypnsapi_models.SendSmsVerifyCodeRequest(
        phone_number=phone,
        sign_name=settings.aliyun_pnvs_sign_name,
        template_code=settings.aliyun_pnvs_template_code,
        template_param='{"code":"##code##","min":"5"}',
        scheme_name=settings.aliyun_pnvs_scheme_name,
        code_length=6,
        valid_time=settings.h5_sms_code_ttl_seconds,
    ), util_models.RuntimeOptions()


def send_sms_code(phone: str) -> None:
    """向手机号发送短信验证码（验证码由阿里云生成）。失败抛 AliyunPnvsError。"""
    client = _get_client()
    if client is None:
        raise AliyunPnvsError("阿里云短信认证 SDK 未安装")
    request, runtime = _send_request(phone)
    try:
        response = client.send_sms_verify_code_with_options(request, runtime)
    except Exception as exc:  # 阿里云 SDK 以 TeaException 表达业务失败
        raise AliyunPnvsError(f"短信发送失败: {getattr(exc, 'message', '') or exc}") from exc
    body = response.body
    if getattr(body, "code", None) != "OK":
        raise AliyunPnvsError(f"短信发送失败: {getattr(body, 'message', '') or '未知错误'}")


def verify_sms_code(phone: str, code: str) -> bool:
    """核验手机号与验证码。验证码不匹配/过期返回 False；服务异常抛 AliyunPnvsError。"""
    client = _get_client()
    if client is None:
        raise AliyunPnvsError("阿里云短信认证 SDK 未安装")
    from alibabacloud_dypnsapi20170525 import models as dypnsapi_models
    from alibabacloud_tea_util import models as util_models

    request = dypnsapi_models.CheckSmsVerifyCodeRequest(
        phone_number=phone,
        verify_code=code,
        scheme_name=settings.aliyun_pnvs_scheme_name,
    )
    try:
        response = client.check_sms_verify_code_with_options(request, util_models.RuntimeOptions())
    except Exception as exc:
        # 带业务错误码的 TeaException（如验证码不匹配/过期）视为校验失败；
        # 其余（网络、鉴权）视为服务不可用。
        if hasattr(exc, "code"):
            return False
        raise AliyunPnvsError(f"验证码校验服务异常: {exc}") from exc
    body = response.body
    return getattr(body, "code", None) == "OK"
