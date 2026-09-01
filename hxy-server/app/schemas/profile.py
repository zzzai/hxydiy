from pydantic import BaseModel, ConfigDict, Field, field_validator


HEALTH_CLAIM_TERMS = (
    "确诊",
    "诊断",
    "治疗",
    "治愈",
    "疗效",
    "处方",
    "疾病",
)


def _reject_health_claim(value: str) -> str:
    text = value.strip()
    if any(term in text for term in HEALTH_CLAIM_TERMS):
        raise ValueError("画像记录仅支持顾客自述和服务观察，不得填写诊断、治疗或治愈宣称")
    return text


class ProfileRecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    tags: list[str] = Field(default_factory=list, max_length=20)
    service_note: str = Field(default="", max_length=1000)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            text = _reject_health_claim(item)
            if not text or len(text) > 32:
                raise ValueError("画像标签长度须为 1 至 32 个字符")
            if text not in cleaned:
                cleaned.append(text)
        return cleaned

    @field_validator("service_note")
    @classmethod
    def validate_service_note(cls, value: str) -> str:
        return _reject_health_claim(value)

