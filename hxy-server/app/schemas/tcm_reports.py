from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


CONSENT_VERSION = "tcm-report-access-v1"
CONSENT_TEXT = "我单独同意使用已验证手机号查询并向本人展示检测报告，包括体质得分、心率、血氧与湿气等健康信息。我可随时撤回；不向店员开放，不用于推送或新增诊断。"


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


class ReportConsentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted: Literal[True]
    version: Literal["tcm-report-access-v1"]


class ReportConsentOut(BaseModel):
    consented: bool
    version: str = CONSENT_VERSION
    notice: str = CONSENT_TEXT
