from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class EntrySessionIn(BaseModel):
    store_id: int
    position_code: str = Field(min_length=1, max_length=32)
    source: str = Field(default="personal_qr", max_length=16)
    device_label: str = Field(default="", max_length=64)


class KioskSessionIn(BaseModel):
    room_id: int
    device_label: str = Field(default="共享 iPad", max_length=64)


class MoveOccupancyIn(BaseModel):
    target_room_id: int
    version: int | None = None
    reason: str = Field(default="顾客核对位置", max_length=256)


class OccupancyActionIn(BaseModel):
    reason: str = Field(default="", max_length=256)
    reason_code: str = Field(default="other", min_length=1, max_length=32)
    target_state: Literal["released", "cleaning"] | None = None
    expected_minutes: int | None = Field(default=None, ge=1, le=480)


class OccupancyOut(BaseModel):
    id: int
    store_id: int
    room_id: int
    selection_session_id: str
    active_room_id: int | None = None
    active_session_id: str | None = None
    status: str
    source: str
    hold_expires_at: datetime | None = None
    expected_end_at: datetime | None = None
    actual_start_at: datetime | None = None
    actual_service_end_at: datetime | None = None
    departed_at: datetime | None = None
    released_at: datetime | None = None
    release_reason: str = ""
    version: int

    model_config = {"from_attributes": True}
