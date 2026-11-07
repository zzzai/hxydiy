from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator


class LearningAssignmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    staff_id: int = Field(gt=0)
    course_id: str = Field(min_length=1, max_length=48)
    course_version: str = Field(min_length=1, max_length=48)
    request_id: str = Field(min_length=8, max_length=100)


class LearningActionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["mark_section", "submit", "follow_up"]
    request_id: str = Field(min_length=8, max_length=100)
    expected_revision: int = Field(ge=0)
    section_id: str | None = Field(default=None, min_length=1, max_length=64)
    answers: dict[str, StrictInt] | None = None
    note: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_action(self):
        permitted = {"mark_section": "section_id", "submit": "answers", "follow_up": "note"}[self.kind]
        if getattr(self, permitted) is None:
            raise ValueError("action payload is missing")
        if any(getattr(self, field) is not None for field in {"section_id", "answers", "note"} - {permitted}):
            raise ValueError("unrelated action payload is forbidden")
        if self.note is not None and not self.note.strip():
            raise ValueError("follow-up note must not be blank")
        if self.answers is not None and len(self.answers) > 100:
            raise ValueError("too many answers")
        return self


class LearningCoachIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assignment_id: str = Field(min_length=1, max_length=36)
    question: str = Field(min_length=1, max_length=500)
    section_id: str | None = Field(default=None, min_length=1, max_length=64)
    request_id: str = Field(min_length=8, max_length=100)

    @model_validator(mode="after")
    def validate_question(self):
        if not self.question.strip():
            raise ValueError("question must not be blank")
        return self


class LearningWeeklyPlanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lookback_days: int = Field(default=14, ge=7, le=30)
