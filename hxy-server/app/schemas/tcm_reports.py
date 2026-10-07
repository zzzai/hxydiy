from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.tcm_original_report import original_link


CONSENT_VERSION = "tcm-report-access-v2-original"
CONSENT_TEXT = "我单独同意使用已验证手机号查询本人健康检测报告，并在有有效来源链接时跳转到检测方原站查看完整报告。完整报告可能包含个人及健康信息，以原站展示为准；DIY不向原站传递我的手机号、登录令牌或读取密钥，不复制报告图片，也不向店员开放、不用于推送或新增诊断。原站链接无需原站登录即可打开，获得链接的人可能查看报告，请勿转发。我可撤回DIY报告查看授权，但撤回不能使已经获得的原站链接失效，也不能阻止他人打开已转发的链接。"


class ReportSummary(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    report_id: str = Field(pattern=r"^[\w-]{1,128}$")
    reported_at: datetime | None = None
    title: Literal["检测报告"] = "检测报告"


class ReportList(BaseModel):
    items: list[ReportSummary] = Field(max_length=20)
    limit: int = Field(ge=1, le=20)
    offset: int = Field(ge=0, le=100000)
    has_more: bool


class PhysiqueScore(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    name: str = Field(max_length=64)
    score: float | None = None


class ReportDetail(ReportSummary):
    physiques: list[PhysiqueScore] = Field(default_factory=list, max_length=9)
    heart_rate: float | None = None
    blood_oxygen: float | None = None
    moisture: int | None = None
    original_report_url: str | None = Field(default=None, max_length=4096)

    @field_validator("original_report_url")
    @classmethod
    def validate_original_report_url(cls, value, info):
        return original_link(value, info.data.get("report_id", ""))


class ReportConsentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted: Literal[True]
    version: Literal["tcm-report-access-v2-original"]


class ReportConsentOut(BaseModel):
    consented: bool
    version: str = CONSENT_VERSION
    notice: str = CONSENT_TEXT
