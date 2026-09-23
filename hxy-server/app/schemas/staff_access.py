from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr


StaffScopeRole = Literal["brand_admin", "hq_operator", "store_manager", "store_staff"]
StaffScopeType = Literal["brand", "store"]
StaffScopeStatus = Literal["active", "disabled"]


class StaffLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: StrictStr = Field(min_length=1, max_length=32)
    password: StrictStr = Field(min_length=1, max_length=128)


class WorkspaceSelectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment_id: StrictInt = Field(gt=0)


class StaffScopeAssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: StaffScopeRole
    scope_type: StaffScopeType
    scope_id: StrictInt | None = Field(default=None, gt=0)


class StaffScopeAssignmentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: StaffScopeStatus


class WorkspaceGrantOut(BaseModel):
    assignment_id: int
    role: StaffScopeRole
    scope_type: StaffScopeType
    scope_id: int | None
    scope_name: str


class StaffSummaryOut(BaseModel):
    id: int
    name: str
    role: str
    store_id: int | None
    technician_id: int | None
    store_name: str


class StaffLoginResponse(BaseModel):
    token: str
    selector_token: str | None
    workspaces: list[WorkspaceGrantOut]
    staff: StaffSummaryOut


class WorkspaceSelectResponse(BaseModel):
    token: str
    workspace: WorkspaceGrantOut
    staff: StaffSummaryOut


class ApiErrorDetail(BaseModel):
    code: str
    message: str


class ApiErrorResponse(BaseModel):
    detail: ApiErrorDetail


class StaffScopeAssignmentOut(BaseModel):
    id: int
    staff_id: int
    role: StaffScopeRole
    scope_type: StaffScopeType
    scope_id: int | None
    status: StaffScopeStatus
    created_by_staff_id: int | None
    created_at: datetime | None
    updated_at: datetime | None


class StaffScopeAssignmentList(BaseModel):
    items: list[StaffScopeAssignmentOut]
    total: int
