"""Project-aware service facts; not medical or marketing profiles."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')


class WaterRecord(StrictRecord):
    request: Literal['lower', 'suitable', 'higher'] | None = None
    action: Literal['lowered', 'raised'] | None = None
    feedback: Literal['suitable', 'still_unsuitable'] | None = None

    @model_validator(mode='after')
    def nonempty(self):
        if not (self.request or self.action or self.feedback):
            raise ValueError('请记录水温要求、处理或反馈')
        return self


class MassageRecord(StrictRecord):
    region: Literal['shoulder', 'neck', 'back', 'waist', 'abdomen', 'arm', 'leg', 'foot']
    side: Literal['left', 'right', 'both', 'unspecified'] = 'unspecified'
    request: Literal['lighter', 'stronger', 'longer', 'avoid'] | None = None
    action: Literal['lighter', 'stronger', 'longer', 'avoided'] | None = None
    feedback: Literal['suitable', 'still_unsuitable'] | None = None

    @model_validator(mode='after')
    def nonempty(self):
        if not (self.request or self.action or self.feedback):
            raise ValueError('请记录这处的要求、处理或反馈')
        return self


class ProjectServiceRecord(StrictRecord):
    schema_version: Literal[6]
    taxonomy_version: Literal['service_record_v1']
    template: Literal['herbal_signature_v1', 'general_v1']
    water: WaterRecord | None = None
    massage: list[MassageRecord] = Field(default_factory=list, max_length=3)
    heat: Literal['too_hot', 'suitable', 'end_early'] | None = None
    heat_note: str = Field(default='', max_length=200)
    communication: Literal['quiet', 'chat'] | None = None
    service_note: str = Field(default='', max_length=200)
    recording_outcome: Literal['no_additional_notes'] | None = None

    @model_validator(mode='after')
    def validate_content(self):
        self.service_note = self.service_note.strip()
        self.heat_note = self.heat_note.strip()
        has_content = bool(self.water or self.massage or self.heat or self.heat_note or self.communication or self.service_note)
        if self.recording_outcome and has_content:
            raise ValueError('本次没有新情况不能与记录内容同时保存')
        if not has_content and not self.recording_outcome:
            raise ValueError('请记录一项内容，或选择本次没有新情况')
        if self.template == 'general_v1' and (self.water or self.massage or self.heat or self.heat_note):
            raise ValueError('当前项目不支持这些服务环节')
        points = [(item.region, item.side) for item in self.massage]
        if len(points) != len(set(points)):
            raise ValueError('同一部位和侧别只记录一次')
        return self

    def storage_payload(self):
        return self.model_dump(mode='json', exclude_none=True, exclude_unset=True)


def safe_service_lines(raw: dict) -> list[str]:
    """Validated code-only summary; never return free text from historical JSON."""
    try:
        record = ProjectServiceRecord.model_validate(raw)
    except (ValueError, TypeError):
        return []
    lines = []
    if record.water:
        water = record.water
        parts = []
        if water.request:
            parts.append({'lower': '顾客希望水温低一点', 'suitable': '顾客表示水温合适', 'higher': '顾客希望水温高一点'}[water.request])
        if water.action:
            parts.append({'lowered': '本次已调低水温', 'raised': '本次已调高水温'}[water.action])
        if water.feedback:
            parts.append({'suitable': '顾客反馈水温合适', 'still_unsuitable': '顾客反馈仍不合适'}[water.feedback])
        lines.append('泡脚：' + '；'.join(parts))
    regions = {'shoulder': '肩部', 'neck': '颈部', 'back': '背部', 'waist': '腰部', 'abdomen': '腹部', 'arm': '手臂', 'leg': '腿部', 'foot': '足部'}
    sides = {'left': '左侧', 'right': '右侧', 'both': '两侧', 'unspecified': ''}
    for item in record.massage:
        parts = []
        if item.request:
            parts.append('顾客要求' + {'lighter': '轻一点', 'stronger': '重一点', 'longer': '多按一会儿', 'avoid': '不要按这里'}[item.request])
        if item.action:
            parts.append({'lighter': '本次已减轻力度', 'stronger': '本次已加重力度', 'longer': '本次已增加按摩时间', 'avoided': '本次已避开'}[item.action])
        if item.feedback:
            parts.append({'suitable': '顾客反馈调整后合适', 'still_unsuitable': '顾客反馈仍不合适'}[item.feedback])
        lines.append(sides[item.side] + regions[item.region] + '：' + '；'.join(parts))
    if record.heat:
        lines.append('热敷：' + {'too_hot': '顾客觉得太烫', 'suitable': '顾客表示温度合适', 'end_early': '顾客要求提前结束'}[record.heat])
    if record.communication:
        lines.append({'quiet': '顾客上次想安静休息', 'chat': '顾客上次愿意聊天'}[record.communication])
    return lines
