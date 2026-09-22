from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from jose import JWTError, jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.staff_access import staff_read_only_request_allowed
from app.models import Staff, StaffScopeAssignment, Store


LEGACY_ROLE_BY_ASSIGNMENT = {
    "brand_admin": "admin",
    "hq_operator": "staff",
    "store_manager": "manager",
    "store_staff": "staff",
}


@dataclass(frozen=True)
class WorkspaceGrant:
    assignment_id: int
    role: str
    scope_type: str
    scope_id: int | None
    scope_name: str

    def as_dict(self) -> dict:
        return {
            "assignment_id": self.assignment_id,
            "role": self.role,
            "scope_type": self.scope_type,
            "scope_id": self.scope_id,
            "scope_name": self.scope_name,
        }


class StaffContext:
    def __init__(self, staff: Staff, assignment: StaffScopeAssignment | None = None):
        self.staff = staff
        self.assignment = assignment

    def __getattr__(self, name: str):
        return getattr(self.staff, name)

    @property
    def assignment_id(self) -> int | None:
        return self.assignment.id if self.assignment else None

    @property
    def assignment_role(self) -> str | None:
        return self.assignment.role if self.assignment else None

    @property
    def scope_type(self) -> str | None:
        return self.assignment.scope_type if self.assignment else None

    @property
    def scope_id(self) -> int | None:
        return self.assignment.scope_id if self.assignment else None

    @property
    def role(self) -> str:
        if self.assignment:
            return LEGACY_ROLE_BY_ASSIGNMENT[self.assignment.role]
        return self.staff.role

    @property
    def store_id(self) -> int | None:
        if self.assignment and self.assignment.scope_type == "store":
            return self.assignment.scope_id
        if self.assignment and self.assignment.scope_type == "brand":
            return None
        return self.staff.store_id


def _auth_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _validate_staff(staff: Staff | None, credentials_version: object) -> Staff:
    if not staff or staff.status != "active":
        raise _auth_error(401, "STAFF_ACCOUNT_UNAVAILABLE", "账号不可用")
    if int(credentials_version or 1) != int(staff.credentials_version or 1):
        raise _auth_error(401, "STAFF_SESSION_REVOKED", "登录状态已失效，请重新登录")
    if staff.temporary_expires_at is not None:
        expires_at = staff.temporary_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= expires_at:
            raise _auth_error(401, "STAFF_ACCOUNT_EXPIRED", "临时账号已过期，请联系管理员")
    return staff


def list_staff_workspaces(db: Session, staff: Staff) -> list[WorkspaceGrant]:
    rows = db.execute(
        select(StaffScopeAssignment, Store.name)
        .outerjoin(Store, StaffScopeAssignment.scope_id == Store.id)
        .where(
            StaffScopeAssignment.staff_id == staff.id,
            StaffScopeAssignment.status == "active",
        )
        .order_by(StaffScopeAssignment.id)
    ).all()
    return [
        WorkspaceGrant(
            assignment_id=assignment.id,
            role=assignment.role,
            scope_type=assignment.scope_type,
            scope_id=assignment.scope_id,
            scope_name=store_name or "荷小悦品牌总部",
        )
        for assignment, store_name in rows
    ]


def assignments_are_not_initialized(db: Session) -> bool:
    return (db.scalar(select(func.count()).select_from(StaffScopeAssignment)) or 0) == 0


def create_selector_token(staff: Staff) -> str:
    payload = {
        "sub": str(staff.id),
        "token_type": "staff_workspace_selector",
        "credentials_version": int(staff.credentials_version or 1),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


create_workspace_selector_token = create_selector_token


def create_scoped_token(staff: Staff, assignment: StaffScopeAssignment) -> str:
    payload = {
        "sub": str(staff.id),
        "token_type": "staff_scope",
        "assignment_id": assignment.id,
        "role": assignment.role,
        "scope_type": assignment.scope_type,
        "scope_id": assignment.scope_id,
        "credentials_version": int(staff.credentials_version or 1),
        "exp": datetime.now(timezone.utc) + timedelta(hours=12),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


create_scoped_staff_token = create_scoped_token


def audit_context(context: StaffContext) -> dict:
    return {
        "assignment_id": context.assignment_id,
        "actor_role": context.assignment_role,
        "scope_type": context.scope_type,
        "scope_id": context.scope_id,
    }


def resolve_selector_staff(token: str, db: Session) -> Staff:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("token_type") != "staff_workspace_selector":
            raise _auth_error(401, "INVALID_TOKEN_TYPE", "令牌类型无效")
        return _validate_staff(db.get(Staff, int(payload["sub"])), payload.get("credentials_version"))
    except HTTPException:
        raise
    except (JWTError, KeyError, TypeError, ValueError):
        raise _auth_error(401, "AUTHENTICATION_EXPIRED", "登录已过期")


def resolve_staff_context(token: str, db: Session) -> StaffContext:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        token_type = payload.get("token_type")
        if token_type not in {"staff", "staff_scope"}:
            raise _auth_error(401, "INVALID_TOKEN_TYPE", "令牌类型无效")
        staff = _validate_staff(db.get(Staff, int(payload["sub"])), payload.get("credentials_version"))
        if token_type == "staff":
            if staff.role == "technician" or assignments_are_not_initialized(db):
                context = StaffContext(staff)
            else:
                assignments = list(db.scalars(
                    select(StaffScopeAssignment)
                    .where(
                        StaffScopeAssignment.staff_id == staff.id,
                        StaffScopeAssignment.status == "active",
                    )
                    .order_by(StaffScopeAssignment.id)
                ))
                if not assignments:
                    raise _auth_error(401, "STAFF_ASSIGNMENT_REVOKED", "当前工作区授权已失效，请重新登录")
                if len(assignments) != 1:
                    raise _auth_error(403, "WORKSPACE_SELECTION_REQUIRED", "请重新登录并选择工作区")
                context = StaffContext(staff, assignments[0])
        else:
            assignment = db.get(StaffScopeAssignment, int(payload["assignment_id"]))
            if (
                not assignment
                or assignment.staff_id != staff.id
                or assignment.status != "active"
                or assignment.role != payload.get("role")
                or assignment.scope_type != payload.get("scope_type")
                or assignment.scope_id != payload.get("scope_id")
            ):
                raise _auth_error(401, "STAFF_ASSIGNMENT_REVOKED", "当前工作区授权已失效，请重新登录")
            if assignment.scope_type == "store" and not db.get(Store, assignment.scope_id):
                raise _auth_error(401, "STAFF_ASSIGNMENT_REVOKED", "当前工作区授权已失效，请重新登录")
            context = StaffContext(staff, assignment)
        if context.role not in {"admin", "manager", "staff", "technician"}:
            raise _auth_error(403, "INVALID_STAFF_ROLE", "员工角色无效")
        if context.role == "technician" and not context.technician_id:
            raise _auth_error(403, "TECHNICIAN_BINDING_REQUIRED", "技师账号未绑定技师档案")
        if context.role == "staff" and context.assignment_role != "hq_operator" and not context.store_id:
            raise _auth_error(403, "STAFF_STORE_REQUIRED", "普通员工必须绑定门店")
        if context.role == "staff" and context.assignment_role != "hq_operator" and not staff_read_only_request_allowed():
            raise _auth_error(403, "STAFF_READ_ONLY", "普通员工仅可查看本店运营信息")
        return context
    except HTTPException:
        raise
    except (JWTError, KeyError, TypeError, ValueError):
        raise _auth_error(401, "AUTHENTICATION_EXPIRED", "登录已过期")
