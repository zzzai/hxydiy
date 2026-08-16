from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class SelectionItemIn(BaseModel):
    project_id: int | str | None = None
    catalog_version_id: int | None = Field(default=None, ge=1)
    option_choice_ids: list[int] = Field(default_factory=list, max_length=40)
    addon_id: int | None = None
    quantity: int = Field(default=1, ge=1, le=20)
    addon_ids: list[int] = Field(default_factory=list)
    diy_preferences: list[str] = Field(default_factory=list)
    item_type: str = "service"
    chargeable: bool = True

    @field_validator("option_choice_ids")
    @classmethod
    def validate_option_choice_ids(cls, value: list[int]) -> list[int]:
        if any(choice_id <= 0 for choice_id in value):
            raise ValueError("option choice ids must be positive")
        if len(value) != len(set(value)):
            raise ValueError("option choice ids must be unique")
        return value


class SelectionSaveIn(BaseModel):
    items: list[SelectionItemIn] = Field(default_factory=list, max_length=50)
    diy_preferences: dict = Field(default_factory=dict)
    device_label: str = Field(default="", max_length=64)


class SelectionCreateIn(BaseModel):
    store_id: int
    source: str = Field(default="in_store", max_length=16)
    device_label: str = Field(default="", max_length=64)


class SelectionSessionOut(BaseModel):
    id: str
    store_id: int
    source: str
    device_label: str
    status: str
    items: list
    diy_preferences: dict
    pricing_snapshot: dict = Field(default_factory=dict)
    store_total_cents: int = 0
    group_total_cents: int = 0
    member_total_cents: int = 0
    expires_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    submitted_at: datetime | None = None
    confirmed_at: datetime | None = None

    model_config = {"from_attributes": True}


class SelectionCreateOut(BaseModel):
    session: SelectionSessionOut
    access_token: str


class MySelectionSessionsOut(BaseModel):
    items: list[SelectionSessionOut]
    total: int
