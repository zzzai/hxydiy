from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置，从环境变量 / .env 读取。真实凭证只进 .env，绝不入库。"""

    app_name: str = "荷小悦顾客端 API"
    environment: str = "local"  # local / test / staging / production
    database_url: str = "sqlite:///./hxy_dev.db"

    # JWT
    jwt_secret: str = "CHANGE_ME_TO_A_LONG_RANDOM_STRING"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 天

    # H5 手机验证码：短信服务接入前，local/test 返回 debug_code，production 永不返回。
    h5_sms_debug: bool = False
    h5_sms_code_ttl_seconds: int = 300
    h5_sms_send_interval_seconds: int = 60
    h5_sms_max_attempts: int = 5

    # 阿里云普通短信：使用已审核的企业签名和验证码模板。
    aliyun_sms_access_key_id: str = ""
    aliyun_sms_access_key_secret: str = ""
    aliyun_sms_sign_name: str = "荷小悦科技"
    aliyun_sms_template_code: str = ""

    @property
    def aliyun_sms_enabled(self) -> bool:
        return bool(self.aliyun_sms_access_key_id and self.aliyun_sms_access_key_secret and self.aliyun_sms_template_code)

    # 阿里云号码认证（短信认证）：配置齐全时走 SendSmsVerifyCode/CheckSmsVerifyCode。
    aliyun_pnvs_access_key_id: str = ""
    aliyun_pnvs_access_key_secret: str = ""
    aliyun_pnvs_scheme_name: str = ""
    aliyun_pnvs_sign_name: str = "速通互联验证码"
    aliyun_pnvs_template_code: str = "100001"

    @property
    def aliyun_pnvs_enabled(self) -> bool:
        return bool(self.aliyun_pnvs_access_key_id and self.aliyun_pnvs_access_key_secret and self.aliyun_pnvs_scheme_name)

    # 第三方会员系统向 DIY 推送手机号会员状态。留空时接口禁用，避免误接收数据。
    third_party_membership_sync_key: str = ""

    occupancy_scheduler_enabled: bool = False
    occupancy_scheduler_observe_only: bool = True
    occupancy_scheduler_interval_seconds: int = 60
    occupancy_closing_hour: int = 3
    occupancy_timezone: str = "Asia/Shanghai"
    h5_public_base_url: str = "https://diy.hexiaoyue.com/"

    # 媒体存储：local 供开发/测试使用；production 使用 qiniu。
    media_storage_backend: str = "local"
    media_storage_root: str = "./media"
    media_max_size_bytes: int = 5 * 1024 * 1024
    media_public_base_url: str = ""
    qiniu_access_key: str = ""
    qiniu_secret_key: str = ""
    qiniu_bucket: str = "diyhxy"
    qiniu_cdn_domain: str = "https://img.hexiaoyue.com"
    qiniu_signed_url_ttl_seconds: int = 600
    # 七牛区域不做猜测；为空时由 SDK 按上传凭证自动探测。
    qiniu_zone: str = ""

    # 微信小程序
    wx_appid: str = ""
    wx_appsecret: str = ""

    # 微信支付 v3（直连商户）
    wxpay_mchid: str = ""
    wxpay_appid: str = ""
    wxpay_apiv3_key: str = ""
    wxpay_cert_serial_no: str = ""
    wxpay_private_key_path: str = ""
    # 验签：微信支付公钥模式（官方推荐，无过期时间）
    wxpay_public_key_id: str = ""
    wxpay_public_key_path: str = ""
    # 灰度兼容：平台证书（切换灰度期内回调/应答可能仍用平台证书签名）
    wxpay_platform_cert_path: str = ""
    wxpay_notify_url: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
