# Wellness Profile Current Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不破坏现有 `schema_version=3 / service_reference_v2` 契约的前提下，建立只由顾客确认记录生成的当前画像、授权基础和可审计读取接口。

**Architecture:** 继续把 `customer_profile_records` 作为不可覆盖的原始事实，在独立投影服务中生成 `customer_profile_current`。普通画像按字段有效期投影；敏感健康相关字段在顾客侧单独授权上线前不进入当前画像。管理端通过门店隔离的只读接口查看投影，不能直接修改投影表。

**Tech Stack:** Python 3.11、FastAPI、Pydantic v2、SQLAlchemy 2、Alembic、PostgreSQL/SQLite 合同测试、pytest。

## Global Constraints

- 最新主干已有 `schema_version=3`、`taxonomy_version=service_reference_v2`；不得改变现有编码语义。
- `schema_version=1` 和 `schema_version=2 / service_reference_v1` 历史记录继续只读兼容。
- 顾客未确认的记录不得进入 `customer_profile_current`。
- `technician_observed` 不得投影为长期顾客画像。
- `service_related_context`、顾客原话、用药、孕产及其他健康相关信息在独立授权能力上线前不得进入当前画像。
- 当前画像只由原始记录重建；任何角色都不得直接写投影表。
- 所有查询先按顾客和门店范围收窄；不得开放跨店顾客搜索。
- 保留现有技师本人完成服务、幂等、审计和活动服务读取边界。
- 不引入 Celery、Kafka、数据仓库、向量数据库或 AI 模型。
- 不读取或依赖 `_build_plan/`。

---

## Program Split

本设计拆为五个可独立验收的实施计划。本文件只实施第 1 个：

1. 当前画像与授权数据底座（本计划）。
2. 匿名转会员确认合并与合并审计。
3. 技师身体图、部位状态和 30 秒 v4 快记。
4. 顾客侧普通/敏感信息确认与撤回。
5. 复购特征、管理端运营视图和行动结果闭环。

后续计划必须消费本计划定义的模型和投影接口，不能另建第二套当前画像。

## File Map

- Create `hxy-server/app/domain/wellness_profile.py`：当前画像允许投影的字段、稳定编码、有效期和扁平化类型。
- Create `hxy-server/app/models/customer_profile_state.py`：当前画像和授权模型。
- Create `hxy-server/app/services/customer_profile_projection.py`：从原始记录重建当前画像。
- Create `hxy-server/alembic/versions/20260906_wellness_profile_current.py`：新表、约束和索引。
- Create `hxy-server/tests/test_wellness_profile_taxonomy.py`：字典和字段白名单合同。
- Create `hxy-server/tests/test_wellness_profile_models.py`：模型与迁移合同。
- Create `hxy-server/tests/test_customer_profile_projection.py`：投影、过期和更正测试。
- Modify `hxy-server/tests/test_technician_profile_v3_contract.py`：写入联动和门店隔离读取测试，复用其真实 v3 API 测试装置。
- Modify `hxy-server/app/models/__init__.py`：导出新模型。
- Modify `hxy-server/app/api/admin_v2.py`：画像写入后触发投影，并增加店长只读接口。
- Create `docs/contracts/wellness-profile-current-v1.md`：跨端当前画像契约。
- Modify `docs/TEAM-MEMORY.md`：登记新契约和后续边界。
- Modify `docs/workstreams/technician.md`：记录本地实现、测试和未发布状态。

### Task 1: 固化当前画像投影字典

**Files:**
- Create: `hxy-server/app/domain/wellness_profile.py`
- Create: `hxy-server/tests/test_wellness_profile_taxonomy.py`
- Create: `docs/contracts/wellness-profile-current-v1.md`

**Interfaces:**
- Consumes: v3 `customer_reported` JSON；现有 `service_reference_v2` 稳定编码。
- Produces: `ProfileProjectionSpec`、`ProjectedProfileValue`、`V3_PROFILE_PROJECTION_SPECS`、`extract_confirmed_v3_profile(profile)`。

- [ ] **Step 1: 写字典失败测试**

```python
from app.domain.wellness_profile import (
    V3_PROFILE_PROJECTION_SPECS,
    extract_confirmed_v3_profile,
)


def test_projection_specs_are_unique_and_exclude_sensitive_paths():
    codes = [item.profile_code for item in V3_PROFILE_PROJECTION_SPECS]
    assert len(codes) == len(set(codes))
    assert all("service_related_context" not in item.source_path for item in V3_PROFILE_PROJECTION_SPECS)
    assert all("technician_observed" not in item.source_path for item in V3_PROFILE_PROJECTION_SPECS)


def test_v3_profile_is_flattened_to_stable_values():
    groups = extract_confirmed_v3_profile({
        "schema_version": 3,
        "taxonomy_version": "service_reference_v2",
        "customer_reported": {
            "force_preference": "medium",
            "focus_areas": ["neck_shoulder", "legs"],
            "personal_context": {"age_band": "35_44"},
            "service_related_context": {
                "contexts": ["medication_mentioned"],
                "quote": "顾客自述正在用药",
            },
        },
        "technician_observed": {"service_feedback": "suitable"},
    })
    values = [item for group in groups.values() for item in group]
    assert {(item.profile_code, item.value) for item in values} == {
        ("force_preference", "medium"),
        ("focus_area", "neck_shoulder"),
        ("focus_area", "legs"),
        ("age_band", "35_44"),
    }
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest tests/test_wellness_profile_taxonomy.py -q`

Expected: FAIL，错误包含 `No module named 'app.domain.wellness_profile'`。

- [ ] **Step 3: 实现最小投影字典**

```python
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProfileProjectionSpec:
    profile_code: str
    source_path: tuple[str, ...]
    valid_days: int
    sensitivity_level: str = "normal"
    multi_value: bool = False


@dataclass(frozen=True)
class ProjectedProfileValue:
    profile_code: str
    value: str
    valid_days: int
    sensitivity_level: str
    multi_value: bool


V3_PROFILE_PROJECTION_SPECS = (
    ProfileProjectionSpec("focus_area", ("customer_reported", "focus_areas"), 180, multi_value=True),
    ProfileProjectionSpec("avoid_area", ("customer_reported", "avoid_areas"), 180, multi_value=True),
    ProfileProjectionSpec("force_preference", ("customer_reported", "force_preference"), 180),
    ProfileProjectionSpec("temperature_preference", ("customer_reported", "temperature_preference"), 180),
    ProfileProjectionSpec("age_band", ("customer_reported", "personal_context", "age_band"), 365),
    ProfileProjectionSpec("body_build", ("customer_reported", "personal_context", "build"), 365),
    ProfileProjectionSpec("height_band", ("customer_reported", "personal_context", "height_band"), 365),
    ProfileProjectionSpec("work_context", ("customer_reported", "work_lifestyle", "occupation_contexts"), 180, multi_value=True),
    ProfileProjectionSpec("sleep_feeling", ("customer_reported", "work_lifestyle", "sleep_quality"), 30),
    ProfileProjectionSpec("decision_focus", ("customer_reported", "communication_consumption", "decision_priorities"), 180, multi_value=True),
)


MISSING = object()


def _read_path(payload: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return MISSING
        if key not in value:
            return MISSING
        value = value[key]
    return value


def extract_confirmed_v3_profile(profile: dict[str, Any]) -> dict[str, list[ProjectedProfileValue]]:
    if profile.get("schema_version") != 3 or profile.get("taxonomy_version") != "service_reference_v2":
        return {}
    result: dict[str, list[ProjectedProfileValue]] = {}
    for spec in V3_PROFILE_PROJECTION_SPECS:
        raw = _read_path(profile, spec.source_path)
        if raw is MISSING:
            continue
        values = raw if spec.multi_value and isinstance(raw, list) else [raw]
        projected: list[ProjectedProfileValue] = []
        for value in values:
            if isinstance(value, str) and value:
                projected.append(ProjectedProfileValue(
                    spec.profile_code, value, spec.valid_days,
                    spec.sensitivity_level, spec.multi_value,
                ))
        result[spec.profile_code] = projected
    return result
```

- [ ] **Step 4: 写跨端合同文档**

在 `docs/contracts/wellness-profile-current-v1.md` 明确：输入版本、允许投影字段、排除字段、有效期、唯一维度、过期语义、店长读取范围，以及当前画像禁止直接写入。

- [ ] **Step 5: 运行测试并提交**

Run: `python -m pytest tests/test_wellness_profile_taxonomy.py -q`

Expected: PASS。

```powershell
git add hxy-server/app/domain/wellness_profile.py hxy-server/tests/test_wellness_profile_taxonomy.py docs/contracts/wellness-profile-current-v1.md
git commit -m "feat(profile): define current profile projection contract"
```

### Task 2: 创建当前画像和授权模型

**Files:**
- Create: `hxy-server/app/models/customer_profile_state.py`
- Create: `hxy-server/alembic/versions/20260906_wellness_profile_current.py`
- Create: `hxy-server/tests/test_wellness_profile_models.py`
- Modify: `hxy-server/app/models/__init__.py`

**Interfaces:**
- Consumes: `users.id`、`customer_profile_records.id`、`selection_sessions.id`。
- Produces: `CustomerProfileCurrent`、`CustomerProfileConsent` SQLAlchemy 模型。

- [ ] **Step 1: 写模型失败测试**

```python
from app.models import CustomerProfileConsent, CustomerProfileCurrent


def test_current_profile_has_rebuildable_source_and_expiry():
    table = CustomerProfileCurrent.__table__
    assert table.c.customer_id.nullable is False
    assert table.c.source_record_id.nullable is False
    assert table.c.valid_until.nullable is False
    assert table.c.profile_value_json.nullable is False
    assert table.c.confirmation_count.nullable is False


def test_profile_consent_is_versioned_and_revocable():
    table = CustomerProfileConsent.__table__
    assert table.c.consent_type.nullable is False
    assert table.c.consent_text_version.nullable is False
    assert table.c.revoked_at.nullable is True
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest tests/test_wellness_profile_models.py -q`

Expected: FAIL，错误包含 `cannot import name 'CustomerProfileCurrent'`。

- [ ] **Step 3: 实现模型**

```python
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CustomerProfileCurrent(Base):
    __tablename__ = "customer_profile_current"
    __table_args__ = (
        UniqueConstraint(
            "customer_id", "profile_code", "profile_value_key", "body_area_code", "body_side",
            name="uq_customer_profile_current_dimension",
        ),
        Index("ix_customer_profile_current_customer_valid", "customer_id", "status", "valid_until"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    profile_code: Mapped[str] = mapped_column(String(64))
    profile_value_key: Mapped[str] = mapped_column(String(128), default="")
    profile_value_json: Mapped[dict] = mapped_column(JSON)
    body_area_code: Mapped[str] = mapped_column(String(64), default="")
    body_side: Mapped[str] = mapped_column(String(16), default="")
    source_record_id: Mapped[int] = mapped_column(ForeignKey("customer_profile_records.id"), index=True)
    first_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confirmation_count: Mapped[int] = mapped_column(Integer, default=1)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    sensitivity_level: Mapped[str] = mapped_column(String(16), default="normal")
    consent_id: Mapped[int | None] = mapped_column(ForeignKey("customer_profile_consents.id"), nullable=True)
    taxonomy_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CustomerProfileConsent(Base):
    __tablename__ = "customer_profile_consents"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    consent_type: Mapped[str] = mapped_column(String(64), index=True)
    purpose: Mapped[str] = mapped_column(String(256))
    data_categories_json: Mapped[list] = mapped_column(JSON, default=list)
    scope_json: Mapped[dict] = mapped_column(JSON, default=dict)
    consent_method: Mapped[str] = mapped_column(String(32))
    consent_text_version: Mapped[str] = mapped_column(String(64))
    selection_session_id: Mapped[str | None] = mapped_column(ForeignKey("selection_sessions.id"), nullable=True, index=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
```

- [ ] **Step 4: 编写迁移**

创建与模型字段一致的两张表。迁移 `revision="20260906_wellness_current"`，`down_revision="20260905_tech_history_v3"`。先创建 `customer_profile_consents`，再创建 `customer_profile_current`；降级按相反顺序删除。PostgreSQL 与 SQLite 测试均使用普通字符串和 JSON 类型，不新增数据库枚举。

- [ ] **Step 5: 导出模型并验证 Alembic 单 head**

在 `app/models/__init__.py` 导入并加入 `__all__`。

Run: `python -m pytest tests/test_wellness_profile_models.py -q`

Run: `python -m alembic heads`

Expected: 测试 PASS，且仅有 `20260906_wellness_current (head)`。

- [ ] **Step 6: 提交**

```powershell
git add hxy-server/app/models/customer_profile_state.py hxy-server/app/models/__init__.py hxy-server/alembic/versions/20260906_wellness_profile_current.py hxy-server/tests/test_wellness_profile_models.py
git commit -m "feat(profile): add current profile and consent storage"
```

### Task 3: 实现可重建的当前画像投影

**Files:**
- Create: `hxy-server/app/services/customer_profile_projection.py`
- Create: `hxy-server/tests/test_customer_profile_projection.py`

**Interfaces:**
- Consumes: `extract_confirmed_v3_profile(profile)`、`CustomerProfileRecord`、`CustomerProfileCurrent`。
- Produces: `rebuild_customer_profile_current(db, *, customer_id: int, now: datetime | None = None) -> list[CustomerProfileCurrent]`。

- [ ] **Step 1: 写未确认、敏感排除和有效期失败测试**

```python
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import hash_password
from app.db.session import Base
from app.models import CustomerProfileRecord, Staff, Store, User
from app.services.customer_profile_projection import rebuild_customer_profile_current


@pytest.fixture
def projection_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as db:
        yield db
    engine.dispose()


def test_rebuild_uses_only_confirmed_non_sensitive_customer_reported_values(projection_db):
    db = projection_db
    store = Store(store_code="projection-store", name="投影测试店", address="测试地址")
    customer = User(openid="projection-customer")
    db.add_all([store, customer])
    db.flush()
    staff = Staff(
        username="projection-manager", password_hash=hash_password("pass"),
        name="店长", role="manager", status="active", store_id=store.id,
    )
    db.add(staff)
    db.flush()
    confirmed = CustomerProfileRecord(
        store_id=store.id, user_id=customer.id, created_by_staff_id=staff.id,
        source="both", profile={}, signals=[], note="",
    )
    unconfirmed = CustomerProfileRecord(
        store_id=store.id, user_id=customer.id, created_by_staff_id=staff.id,
        source="service_observation", profile={}, signals=[], note="",
    )
    db.add_all([confirmed, unconfirmed])
    db.flush()
    confirmed.customer_confirmed = True
    confirmed.confirmed_at = datetime(2026, 9, 6, tzinfo=timezone.utc)
    confirmed.schema_version = 3
    confirmed.taxonomy_version = "service_reference_v2"
    confirmed.profile = {
        "schema_version": 3,
        "taxonomy_version": "service_reference_v2",
        "customer_reported": {
            "force_preference": "medium",
            "service_related_context": {"contexts": ["medication_mentioned"]},
        },
    }
    unconfirmed.customer_confirmed = False
    unconfirmed.profile = {
        "schema_version": 3,
        "taxonomy_version": "service_reference_v2",
        "customer_reported": {"force_preference": "strong"},
    }
    db.commit()

    rows = rebuild_customer_profile_current(
        db, customer_id=customer.id,
        now=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )

    assert [(row.profile_code, row.profile_value_json["value"]) for row in rows] == [
        ("force_preference", "medium"),
    ]
    assert rows[0].valid_until == datetime(2027, 3, 5, tzinfo=timezone.utc)
```

- [ ] **Step 2: 写更正替代失败测试**

创建两条已确认记录，第二条 `correction_of_id` 指向第一条；重建后断言只使用第二条。再创建未确认更正指向第二条，断言第二条也不再保持有效，当前画像中对应值消失。

- [ ] **Step 3: 运行测试并确认失败**

Run: `python -m pytest tests/test_customer_profile_projection.py -q`

Expected: FAIL，错误包含 `No module named 'app.services.customer_profile_projection'`。

- [ ] **Step 4: 实现重建算法**

```python
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.wellness_profile import ProjectedProfileValue, extract_confirmed_v3_profile
from app.models import CustomerProfileCurrent, CustomerProfileRecord


def rebuild_customer_profile_current(
    db: Session, *, customer_id: int, now: datetime | None = None,
) -> list[CustomerProfileCurrent]:
    current_time = now or datetime.now(timezone.utc)
    records = list(db.scalars(
        select(CustomerProfileRecord)
        .where(CustomerProfileRecord.user_id == customer_id)
        .order_by(CustomerProfileRecord.created_at.asc(), CustomerProfileRecord.id.asc())
    ))
    superseded = {row.correction_of_id for row in records if row.correction_of_id is not None}
    latest_by_code: dict[str, tuple[CustomerProfileRecord, list[ProjectedProfileValue]]] = {}
    confirmation_counts: dict[tuple[str, str], int] = {}
    first_confirmed: dict[tuple[str, str], datetime] = {}
    for record in records:
        if record.id in superseded or not record.customer_confirmed or record.confirmed_at is None:
            continue
        for profile_code, values in extract_confirmed_v3_profile(record.profile or {}).items():
            latest_by_code[profile_code] = (record, values)
            for value in values:
                key = (profile_code, value.value)
                confirmation_counts[key] = confirmation_counts.get(key, 0) + 1
                first_confirmed.setdefault(key, record.confirmed_at)

    db.execute(delete(CustomerProfileCurrent).where(CustomerProfileCurrent.customer_id == customer_id))
    created: list[CustomerProfileCurrent] = []
    for profile_code, (record, values) in latest_by_code.items():
        for value in values:
            key = (profile_code, value.value)
            valid_until = record.confirmed_at + timedelta(days=value.valid_days)
            row = CustomerProfileCurrent(
                customer_id=customer_id,
                profile_code=profile_code,
                profile_value_key=value.value,
                profile_value_json={"value": value.value},
                body_area_code="",
                body_side="",
                source_record_id=record.id,
                first_confirmed_at=first_confirmed[key],
                last_confirmed_at=record.confirmed_at,
                confirmation_count=confirmation_counts[key],
                valid_until=valid_until,
                sensitivity_level=value.sensitivity_level,
                taxonomy_version=record.taxonomy_version or "",
                status="active" if valid_until > current_time else "expired",
            )
            db.add(row)
            created.append(row)
    db.flush()
    return created
```

上述按 `profile_code` 整组替换：单值字段只保留最新值，多值字段使用最新已确认记录的完整数组，显式空数组会清空该字段，不能把历次数组无限并集。测试必须覆盖单值替换、多值替换和空数组清空。

- [ ] **Step 5: 运行投影测试**

Run: `python -m pytest tests/test_customer_profile_projection.py -q`

Expected: PASS。

- [ ] **Step 6: 提交**

```powershell
git add hxy-server/app/services/customer_profile_projection.py hxy-server/tests/test_customer_profile_projection.py
git commit -m "feat(profile): project confirmed records into current profile"
```

### Task 4: 将投影接入画像写入事务

**Files:**
- Modify: `hxy-server/app/api/admin_v2.py:2563-2720`
- Modify: `hxy-server/tests/test_technician_profile_v3_contract.py`

**Interfaces:**
- Consumes: `rebuild_customer_profile_current(db, customer_id=body.user_id)`。
- Produces: 已确认画像保存或更正后，同一事务内完成当前画像重建。

- [ ] **Step 1: 写写入联动失败测试**

```python
def test_confirmed_v3_write_updates_current_profile(self):
    payload = self.v3_payload()
    response = self.client.post(
        "/api/v1/admin/v2/customer-profile-records",
        json=payload,
        headers={**self.technician_headers, "Idempotency-Key": "current-profile-write-001"},
    )
    assert response.status_code == 200
    with self.SessionLocal() as db:
        rows = db.query(CustomerProfileCurrent).filter_by(customer_id=self.user_id).all()
        assert {(row.profile_code, row.profile_value_key) for row in rows} >= {
            ("age_band", "25_34"),
            ("work_context", "desk_work"),
        }


def test_unconfirmed_write_does_not_replace_confirmed_current_profile(self):
    confirmed = self.v3_payload()
    confirmed["profile"]["customer_reported"]["force_preference"] = "medium"
    self.client.post("/api/v1/admin/v2/customer-profile-records", json=confirmed, headers={**self.technician_headers, "Idempotency-Key": "current-profile-write-002"})
    pending = self.v3_payload(customer_confirmed=False)
    pending["profile"]["customer_reported"]["force_preference"] = "strong"
    response = self.client.post("/api/v1/admin/v2/customer-profile-records", json=pending, headers={**self.technician_headers, "Idempotency-Key": "current-profile-write-003"})
    assert response.status_code == 200
    with self.SessionLocal() as db:
        row = db.query(CustomerProfileCurrent).filter_by(customer_id=self.user_id, profile_code="force_preference").one()
        assert row.profile_value_key == "medium"
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest tests/test_technician_profile_v3_contract.py -q`

Expected: FAIL，因为保存后尚未生成当前画像。

- [ ] **Step 3: 接入投影**

在 `CustomerProfileRecord` `db.add(record)` 后先 `db.flush()`，再调用：

```python
from app.services.customer_profile_projection import rebuild_customer_profile_current


rebuild_customer_profile_current(db, customer_id=body.user_id)
```

调用必须处于现有提交事务内。幂等重放返回已存在记录时不得重复创建投影行；更正记录保存后必须重建。投影异常使整个请求回滚，不得留下“原始记录成功、当前画像失败”的半状态。

- [ ] **Step 4: 运行写入与旧版本回归**

Run: `python -m pytest tests/test_profile_record_contract.py tests/test_technician_profile_v3_contract.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add hxy-server/app/api/admin_v2.py hxy-server/tests/test_technician_profile_v3_contract.py
git commit -m "feat(profile): update current profile after confirmed writes"
```

### Task 5: 增加门店隔离的当前画像只读接口

**Files:**
- Modify: `hxy-server/app/api/admin_v2.py:2720-2740`
- Modify: `hxy-server/tests/test_technician_profile_v3_contract.py`

**Interfaces:**
- Consumes: `CustomerProfileCurrent` 最新投影。
- Produces: `GET /api/v1/admin/v2/users/{user_id}/customer-profile-current?include_expired=false`。

- [ ] **Step 1: 写权限和响应失败测试**

```python
def test_manager_reads_current_profile_only_for_own_store_customer(self):
    saved = self.client.post(
        "/api/v1/admin/v2/customer-profile-records", json=self.v3_payload(),
        headers={**self.technician_headers, "Idempotency-Key": "current-profile-read-001"},
    )
    assert saved.status_code == 200
    with self.SessionLocal() as db:
        manager = Staff(
            username="current-profile-manager", password_hash=hash_password("pass"),
            name="店长", role="manager", status="active", store_id=1,
        )
        other_store = Store(store_code="current-profile-other", name="其他店", address="其他地址")
        db.add_all([manager, other_store])
        db.flush()
        other_manager = Staff(
            username="current-profile-other-manager", password_hash=hash_password("pass"),
            name="其他店长", role="manager", status="active", store_id=other_store.id,
        )
        db.add(other_manager)
        db.commit()
        manager_headers = {"Authorization": f"Bearer {create_staff_token(manager.id, 'manager')}"}
        other_headers = {"Authorization": f"Bearer {create_staff_token(other_manager.id, 'manager')}"}

    own = self.client.get(f"/api/v1/admin/v2/users/{self.user_id}/customer-profile-current", headers=manager_headers)
    assert own.status_code == 200
    assert {item["profile_code"] for item in own.json()["items"]} >= {"age_band", "work_context"}
    assert "service_related_context" not in own.text

    other = self.client.get(f"/api/v1/admin/v2/users/{self.user_id}/customer-profile-current", headers=other_headers)
    assert other.status_code == 404


def test_current_profile_excludes_expired_by_default(self):
    with self.SessionLocal() as db:
        manager = Staff(
            username="expired-profile-manager", password_hash=hash_password("pass"),
            name="店长", role="manager", status="active", store_id=1,
        )
        source = CustomerProfileRecord(
            store_id=1, user_id=self.user_id, created_by_staff_id=self.staff_id,
            source="both", schema_version=3, taxonomy_version="service_reference_v2",
            customer_confirmed=True, confirmed_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            profile={"schema_version": 3, "taxonomy_version": "service_reference_v2", "customer_reported": {"force_preference": "medium"}}, signals=[], note="",
        )
        db.add_all([manager, source])
        db.flush()
        rebuild_customer_profile_current(db, customer_id=self.user_id, now=datetime.now(timezone.utc))
        db.commit()
        headers = {"Authorization": f"Bearer {create_staff_token(manager.id, 'manager')}"}
    response = self.client.get(f"/api/v1/admin/v2/users/{self.user_id}/customer-profile-current", headers=headers)
    assert response.status_code == 200
    assert response.json()["items"] == []
```

在测试文件顶部补充 `CustomerProfileCurrent`、`rebuild_customer_profile_current` 导入；现有 `Staff`、`Store`、`CustomerProfileRecord`、`create_staff_token`、`hash_password`、`datetime` 和 `timezone` 直接复用。

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest tests/test_technician_profile_v3_contract.py -q`

Expected: FAIL，接口返回 404 或 405。

- [ ] **Step 3: 实现只读接口**

```python
@router.get("/users/{user_id}/customer-profile-current")
def get_customer_profile_current(
    user_id: int,
    include_expired: bool = False,
    db: Session = Depends(get_db),
    staff: Staff = Depends(require_staff),
):
    if staff.role not in {"manager", "admin"}:
        raise HTTPException(status_code=403, detail="当前账号无权查看顾客当前画像")
    _require_store_user(db, user_id, staff)
    stmt = select(CustomerProfileCurrent).where(CustomerProfileCurrent.customer_id == user_id)
    if not include_expired:
        stmt = stmt.where(
            CustomerProfileCurrent.status == "active",
            CustomerProfileCurrent.valid_until > datetime.now(timezone.utc),
        )
    rows = db.scalars(stmt.order_by(CustomerProfileCurrent.profile_code, CustomerProfileCurrent.id)).all()
    return {
        "items": [{
            "profile_code": row.profile_code,
            "value": row.profile_value_json,
            "body_area_code": row.body_area_code or None,
            "body_side": row.body_side or None,
            "last_confirmed_at": row.last_confirmed_at,
            "valid_until": row.valid_until,
            "taxonomy_version": row.taxonomy_version,
            "status": row.status,
        } for row in rows]
    }
```

`_require_store_user` 继续以本店订单/选单关系验证顾客范围。接口不返回顾客原话、敏感健康字段、创建技师、联系方式或消费金额。

- [ ] **Step 4: 写读取审计断言**

成功读取至少一条当前画像时写 `manager_view_customer_profile_current` 审计，包含门店、顾客、返回字段编码和数量，不复制画像值。空结果不写敏感读取审计。

- [ ] **Step 5: 运行权限回归并提交**

Run: `python -m pytest tests/test_technician_profile_v3_contract.py tests/test_admin_scrm_store_scope.py -q`

Expected: PASS。

```powershell
git add hxy-server/app/api/admin_v2.py hxy-server/tests/test_technician_profile_v3_contract.py
git commit -m "feat(admin): expose store-scoped current profile"
```

### Task 6: 完成契约、回归和本地交付记录

**Files:**
- Modify: `docs/contracts/wellness-profile-current-v1.md`
- Modify: `docs/TEAM-MEMORY.md`
- Modify: `docs/workstreams/technician.md`

**Interfaces:**
- Consumes: Tasks 1–5 的最终模型、接口和测试结果。
- Produces: 三窗口可读取的合并候选事实；不写生产发布事实。

- [ ] **Step 1: 更新共享契约**

在合同文档中写入实际模型字段、索引、API 请求/响应示例、过期判断、审计动作、v1/v2/v3 兼容和敏感字段排除清单。内容必须与最终代码逐字段一致。

- [ ] **Step 2: 更新共享记忆和技师工作流**

在 `docs/TEAM-MEMORY.md` 登记：当前画像只由顾客已确认的 v3 安全字段投影，敏感信息暂不进入；管理端只读且门店隔离。

在 `docs/workstreams/technician.md` 记录修改文件、测试结果、提交状态，以及“未合并、未发布、未完成门店验收”。不要修改 `docs/CURRENT-STATE.md` 或在 `docs/WORK-STATUS.md` 写生产事实。

- [ ] **Step 3: 运行完整专项**

Run:

```powershell
python -m pytest tests/test_wellness_profile_taxonomy.py tests/test_wellness_profile_models.py tests/test_customer_profile_projection.py tests/test_profile_record_contract.py tests/test_technician_profile_v3_contract.py tests/test_h5_auth_api.py tests/test_admin_scrm_store_scope.py -q
```

Expected: 全部 PASS，仅允许已知的 Starlette/httpx 弃用警告。

- [ ] **Step 4: 验证迁移和代码质量**

Run:

```powershell
python -m alembic heads
python -m alembic upgrade head
python -m alembic downgrade 20260905_tech_history_v3
python -m alembic upgrade head
git diff --check
```

Expected: 始终只有一个 Alembic head；升级、降级、再次升级成功；`git diff --check` 无输出。

- [ ] **Step 5: 提交文档并检查分支**

```powershell
git add docs/contracts/wellness-profile-current-v1.md docs/TEAM-MEMORY.md docs/workstreams/technician.md
git commit -m "docs: record current wellness profile contract"
git status --short
git log --oneline origin/main..HEAD
```

Expected: 工作区干净；提交列表只包含本计划范围内的契约、模型、服务、API、测试和文档。

## Completion Gate

本计划只有在以下条件全部满足后才算本地完成：

- 当前画像可以从原始记录完整重建。
- 未确认记录、技师观察、顾客原话和敏感相关情况不会进入当前画像。
- 更正记录正确替代旧记录。
- 默认读取不返回过期值。
- 管理端读取严格门店隔离且带审计。
- v1/v2/v3 历史兼容测试通过。
- Alembic 保持单 head 且升级/降级演练通过。
- 文档明确记录“未合并、未发布、未现场验收”。

完成后再编写并执行第 2 个计划“匿名转会员确认合并”，不得在本计划中顺带实现顾客确认页面、技师身体图或复购运营。
