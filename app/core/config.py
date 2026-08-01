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
    wxpay_notify_url: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
