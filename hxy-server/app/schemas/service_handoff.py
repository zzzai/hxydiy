"""Compact post-service handoff facts for the next technician."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")


AgeBand = Literal[
    "age_25_29",
    "age_30_34",
    "age_35_39",
    "age_40_44",
    "age_45_49",
    "age_50_59",
    "age_60_plus",
]
Gender = Literal["male", "female"]
Communication = Literal["quiet", "chat"]
BodyRegion = Literal["neck_shoulder", "waist_back", "leg", "knee", "foot"]
NextAction = Literal["focus", "lighter", "avoid", "confirm"]
SessionChange = Literal[
    "pressure_lighter",
    "pressure_stronger",
    "temperature_lower",
    "temperature_higher",
    "pace_slower",
    "ended_early",
]


class BasicInfo(StrictRecord):
    age_band: AgeBand | None = None
    gender: Gender | None = None


class BodyFocus(StrictRecord):
    region: BodyRegion
    next_action: NextAction


class ServiceHandoffRecord(StrictRecord):
    schema_version: Literal[7]
    taxonomy_version: Literal["service_handoff_v1"]
    communication: Communication | None = None
    body_focus: list[BodyFocus] = Field(default_factory=list, max_length=3)
    session_changes: list[SessionChange] = Field(default_factory=list, max_length=3)
    basic_info: BasicInfo | None = None
    private_note: str = Field(default="", max_length=200)
    recording_outcome: Literal["no_additional_notes"] | None = None

    @model_validator(mode="after")
    def validate_content(self):
        self.private_note = self.private_note.strip()
        regions = [item.region for item in self.body_focus]
        if len(regions) != len(set(regions)):
            raise ValueError("同一部位只记录一次")
        if len(self.session_changes) != len(set(self.session_changes)):
            raise ValueError("同一变化只记录一次")
        has_basic_info = bool(self.basic_info and (self.basic_info.age_band or self.basic_info.gender))
        has_content = bool(
            self.communication
            or self.body_focus
            or self.session_changes
            or has_basic_info
            or self.private_note
        )
        if self.recording_outcome and has_content:
            raise ValueError("本次没有新情况不能与记录内容同时保存")
        if not has_content and not self.recording_outcome:
            raise ValueError("请记录一项内容，或选择本次没有新情况")
        return self

    def storage_payload(self) -> dict:
        return self.model_dump(mode="json", exclude_none=True, exclude_unset=True)


def safe_handoff_lines(raw: dict) -> list[str]:
    """Return validated service-only facts and exclude free text and basic identity."""
    try:
        record = ServiceHandoffRecord.model_validate(raw)
    except (ValueError, TypeError):
        return []

    lines: list[str] = []
    if record.communication:
        lines.append({"quiet": "顾客想安静休息", "chat": "顾客愿意聊天"}[record.communication])

    regions = {
        "neck_shoulder": "肩颈",
        "waist_back": "腰背",
        "leg": "腿部",
        "knee": "膝盖",
        "foot": "足部",
    }
    actions = {
        "focus": "下次重点加强",
        "lighter": "下次轻一些",
        "avoid": "下次避开",
        "confirm": "下次先确认",
    }
    for item in record.body_focus:
        lines.append(f"{regions[item.region]}：{actions[item.next_action]}")

    changes = {
        "pressure_lighter": "本次已减轻力度",
        "pressure_stronger": "本次已加重力度",
        "temperature_lower": "本次已调低温度",
        "temperature_higher": "本次已调高温度",
        "pace_slower": "本次已放慢节奏",
        "ended_early": "本次已提前结束",
    }
    lines.extend(changes[item] for item in record.session_changes)
    return lines
