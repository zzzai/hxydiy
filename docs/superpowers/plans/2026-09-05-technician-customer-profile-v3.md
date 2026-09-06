# 技师端顾客画像 v3 与本人服务历史 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让技师以分层快记记录可确认的顾客服务画像 v3，并能查看本人真实完成过的服务历史。

**Architecture:** 后端将 v3 定义为版本化、严格校验的画像载荷，并通过只读标签字典让三端共享编码。服务位占用在首次确认时持久关联实际服务技师，历史接口只从这条关联读取本人已完成服务；前端以默认快记、折叠扩展区、确认摘要和专用历史卡片消费这些接口。

**Tech Stack:** FastAPI、Pydantic v2、SQLAlchemy、Alembic、PostgreSQL、React 18、TypeScript、Ant Design、Node test runner。

## Global Constraints

- 新记录使用 `schema_version=3`、`taxonomy_version=service_reference_v2`；v1/v2 记录保持可读。
- 后端保存稳定英文编码；中文文案由版本化字典输出，不以自由中文作为分析维度。
- 默认快记目标为 30–60 秒；扩展字段全为可选，保存仍至少需要一项有效内容。
- 长期画像必须保存来源与顾客确认；未确认记录不进入跨次安全摘要和分析。
- 顾客主动说出的相关情况可记录为原话，但不得生成诊断、治疗、用药建议或差别定价。
- 历史页只显示当前技师 `serviced_by_technician_id` 已关联的服务；旧记录无法唯一关联时不猜测归属。
- 每一项跨端契约变化须同 PR 更新合同测试、`docs/contracts/`、`docs/TEAM-MEMORY.md` 和三端 workstream。

---

### Task 1: 定义 v3 标签字典和严格请求模型

**Files:**
- Modify: `hxy-server/app/api/admin_v2.py:1989-2125`
- Create: `hxy-server/tests/test_technician_profile_v3_contract.py`
- Modify: `admin-react/src/technician/serviceReference.ts`
- Test: `admin-react/tests/service-reference.test.ts`

**Interfaces:**
- Produces: `GET /api/v1/technician/service-reference-taxonomy`，返回 `schema_version`、`taxonomy_version` 以及包含职业场景、基础背景、服务过程反应编码的 `groups`。
- Produces: `CustomerProfileRecordIn` 接受 `schema_version=3` 和 `ServiceReferenceV3Profile`。
- Consumes: 既有 v2 `CustomerProfileRecordIn` 和 `createCustomerProfileRecord`，不得破坏旧调用。

- [ ] **Step 1: 写后端失败合同测试**

```python
def test_v3_profile_accepts_confirmed_customer_context_and_rejects_unknown_codes(client, technician_headers):
    payload = v3_payload(
        customer_reported={
            "personal_context": {"age_band": "25_34", "build": "balanced"},
            "work_lifestyle": {"occupation_contexts": ["desk_work"], "sleep_quality": "average"},
            "service_related_context": {"contexts": ["medication_mentioned"], "quote": "顾客自述正在用药"},
        },
        customer_confirmed=True,
    )
    assert client.post("/api/v1/admin/v2/customer-profile-records", json=payload, headers=technician_headers).status_code == 200
    payload["profile"]["customer_reported"]["personal_context"]["age_band"] = "guess"
    assert client.post("/api/v1/admin/v2/customer-profile-records", json=payload, headers=technician_headers).status_code == 422

def test_taxonomy_endpoint_exposes_v3_stable_codes(client, technician_headers):
    body = client.get("/api/v1/technician/service-reference-taxonomy", headers=technician_headers).json()
    assert body["schema_version"] == 3
    assert body["taxonomy_version"] == "service_reference_v2"
    assert "desk_work" in body["groups"]["occupation_contexts"]
```

- [ ] **Step 2: 运行失败测试**

Run: `pytest hxy-server/tests/test_technician_profile_v3_contract.py -q`

Expected: FAIL，因为 v3 模型和字典端点不存在。

- [ ] **Step 3: 实现最小严格模型与字典端点**

在 `admin_v2.py` 增加 `ServiceReferenceV3CustomerReported`、`ServiceReferenceV3TechnicianObserved`、`ServiceReferenceV3NextVisit` 和 `ServiceReferenceV3Profile`；所有枚举使用明确的 `Literal` 编码集合，数组用 `set`/长度校验拒绝未知编码和重复项。顶层校验接受 1、2、3 三种 schema，只允许 v3 使用 `service_reference_v2`。

在 `technician.py` 追加只读端点，并返回前端所需的编码/中文文案，例如：

```python
SERVICE_REFERENCE_V2_TAXONOMY = {
    "occupation_contexts": {"desk_work": "久坐办公", "standing_work": "久站服务"},
    "body_context": {"height_band": {"shorter": "偏矮", "average": "适中", "taller": "偏高"}},
    "session_response": {"relaxation": {"quick": "较快", "gradual": "逐渐", "tense": "始终较紧张"}},
}

@router.get("/service-reference-taxonomy")
def get_service_reference_taxonomy(
    authorization: str | None = Header(None), db: Session = Depends(get_db)
) -> dict:
    current_technician(authorization, db)
    return {"schema_version": 3, "taxonomy_version": "service_reference_v2", "groups": SERVICE_REFERENCE_V2_TAXONOMY}
```

- [ ] **Step 4: 更新前端纯载荷构造器**

将 `ServiceReferenceInput` 扩展为 v3 分层字段，新增 `buildServiceReferenceV3Payload(userId: number, selectionSessionId: string, values: ServiceReferenceInput)`。载荷必须固定输出：

```ts
{
  schema_version: 3,
  taxonomy_version: 'service_reference_v2',
  customer_confirmed: values.customerConfirmed,
  profile: { schema_version: 3, taxonomy_version: 'service_reference_v2', customer_reported, technician_observed, next_visit },
  signals: [], note: ''
}
```

- [ ] **Step 5: 运行通过测试**

Run: `pytest hxy-server/tests/test_technician_profile_v3_contract.py -q && npm test -- --test-name-pattern="服务参考"`

Expected: v3 合同、旧 v2 合同和前端编码测试全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add hxy-server/app/api/admin_v2.py hxy-server/app/api/technician.py hxy-server/tests/test_technician_profile_v3_contract.py admin-react/src/technician/serviceReference.ts admin-react/tests/service-reference.test.ts
git commit -m "feat(technician): add versioned profile v3 taxonomy"
```

### Task 2: 持久关联实际服务技师并提供本人历史 API

**Files:**
- Modify: `hxy-server/app/models/occupancy.py`
- Create: `hxy-server/alembic/versions/20260905_technician_service_history_v3.py`
- Modify: `hxy-server/app/api/technician.py:314-370`
- Create: `hxy-server/tests/test_technician_service_history_api.py`

**Interfaces:**
- Produces: `PositionOccupancy.serviced_by_technician_id: int | None`。
- Produces: `GET /api/v1/technician/service-history?page=1&page_size=20&profile_status=all`。
- Consumes: `PositionOccupancy.actual_start_at`、`actual_service_end_at`、`SelectionSession`、`CustomerProfileRecord`。

- [ ] **Step 1: 写失败测试**

```python
def test_confirm_binds_technician_and_history_returns_only_own_finished_services(client, db, tech_a_headers, tech_b_headers):
    occupancy = make_active_occupancy(db)
    assert client.post(f"/api/v1/technician/occupancies/{occupancy.id}/confirm", json={"idempotency_key": "history-confirm-a"}, headers=tech_a_headers).status_code == 200
    finish_occupancy(client, occupancy.id, tech_a_headers)
    own = client.get("/api/v1/technician/service-history", headers=tech_a_headers).json()
    other = client.get("/api/v1/technician/service-history", headers=tech_b_headers).json()
    assert own["total"] == 1
    assert other["total"] == 0

def test_ambiguous_legacy_occupancy_is_not_backfilled_to_a_technician(db, alembic_upgrade):
    ambiguous_occupancy = make_legacy_occupancy_with_two_distinct_technician_actions(db)
    alembic_upgrade("20260905_technician_service_history_v3")
    assert ambiguous_occupancy.serviced_by_technician_id is None
```

- [ ] **Step 2: 运行失败测试**

Run: `pytest hxy-server/tests/test_technician_service_history_api.py -q`

Expected: FAIL，因为模型字段、迁移和历史端点尚不存在。

- [ ] **Step 3: 添加模型和 Alembic 迁移**

模型字段和索引：

```python
serviced_by_technician_id: Mapped[int | None] = mapped_column(ForeignKey("technicians.id"), nullable=True, index=True)
```

迁移增加字段和复合索引 `ix_position_occupancies_store_technician_finished`。迁移回填仅选择同一 occupancy 的 `technician_confirm_service`/`technician_finish_service` 审计记录能解析为唯一 `Staff.technician_id` 的情况；多名候选或无候选保持 `NULL`。

- [ ] **Step 4: 将确认动作绑定到实际技师**

在 `_action(...)` 调用 `_occupancy_action(...)` 前：若 `action == "confirm"` 且字段为空，写入 `technician.id`；若已绑定其他技师，返回 `409 TECHNICIAN_SERVICE_OWNER_MISMATCH`。结束服务时也校验已绑定的是当前技师。

- [ ] **Step 5: 实现历史端点**

按 `(store_id, serviced_by_technician_id, actual_service_end_at)` 查询已结束 occupancy，联结选单和顾客，返回脱敏顾客、项目名称、时长、服务位和最新 v2/v3 已确认摘要：

```python
return {
  "items": [{"occupancy_id": 41, "completed_at": "2026-09-05T15:30:00+08:00", "duration_minutes": 60, "profile_status": "confirmed"}],
  "total": total, "page": page, "page_size": page_size,
}
```

不得返回电话、价格、会员、自由原话、疾病名、药品名、孕产描述或其他技师数据。

- [ ] **Step 6: 运行通过测试与迁移检查**

Run: `pytest hxy-server/tests/test_technician_service_history_api.py hxy-server/tests/test_technician_portal_api.py -q && cd hxy-server && alembic heads && alembic check`

Expected: 测试 PASS，只有一个 Alembic head。

- [ ] **Step 7: 提交**

```bash
git add hxy-server/app/models/occupancy.py hxy-server/alembic/versions/20260905_technician_service_history_v3.py hxy-server/app/api/technician.py hxy-server/tests/test_technician_service_history_api.py
git commit -m "feat(technician): persist own service history"
```

### Task 3: 实现分层快记、顾客确认摘要和本人历史页面

**Files:**
- Modify: `admin-react/src/technician/TechnicianProfileSheet.tsx`
- Modify: `admin-react/src/technician/technician-mobile.css`
- Create: `admin-react/src/technician/TechnicianServiceHistoryPage.tsx`
- Modify: `admin-react/src/technician/TechnicianHistoryPage.tsx`
- Modify: `admin-react/src/api.ts`
- Create: `admin-react/tests/technician-profile-v3.test.ts`
- Modify: `admin-react/tests/technician-mobile.test.ts`

**Interfaces:**
- Consumes: `buildServiceReferenceV3Payload` 和 `/technician/service-history`。
- Produces: 可保存的 v3 快记 UI；本人历史卡片 UI。

- [ ] **Step 1: 写前端失败测试**

```ts
test('v3 快记默认展示高频项并把扩展维度放在折叠区', () => {
  const source = read('src/technician/TechnicianProfileSheet.tsx');
  assert.match(source, /本次重点/);
  assert.match(source, /更多服务记忆/);
  assert.match(source, /已向顾客复述并确认/);
});

test('本人历史使用技师专用接口而不是门店级 service-orders', () => {
  assert.match(read('src/api.ts'), /\/technician\/service-history/);
  assert.doesNotMatch(read('src/technician/TechnicianHistoryPage.tsx'), /ServiceOrderList/);
});
```

- [ ] **Step 2: 运行失败测试**

Run: `npm test -- --test-name-pattern="v3 快记|本人历史"`

Expected: FAIL，因为页面和 API 尚未切换。

- [ ] **Step 3: 实现移动端快记层级**

保留现有高频六组，增加 `Collapse` 的“更多服务记忆”。每个组使用 `Tag.CheckableTag` 或 `Radio.Group`，并且仅在已选时写入载荷。相关情况原话最多 100 字，显示“顾客自述，服务前请再次确认”；消费组仅展示预算/决策偏好，不展示收入字段。

保存前显示 `Modal`/抽屉内摘要，必须由技师选择“顾客已确认”才能成为长期画像；未确认仍可保存为本次观察。

- [ ] **Step 4: 实现本人历史页面**

增加：

```ts
export const getTechnicianServiceHistory = (page = 1, pageSize = 20, profileStatus = 'all') =>
  client.get('/technician/service-history', { params: { page, page_size: pageSize, profile_status: profileStatus } });
```

历史页使用移动卡片而不是桌面 `Table`；渲染日期、服务位、项目、时长、脱敏顾客、确认状态和安全摘要。空状态必须区分“尚无本人已完成服务”“旧数据未关联”“加载失败”。

- [ ] **Step 5: 运行通过测试、TypeScript 与构建**

Run: `npm test && npm run build`

Expected: 全部前端测试 PASS，生产构建完成；记录既有大 chunk 警告但不在本任务重构。

- [ ] **Step 6: 提交**

```bash
git add admin-react/src/technician admin-react/src/api.ts admin-react/tests/technician-profile-v3.test.ts admin-react/tests/technician-mobile.test.ts
git commit -m "feat(technician): add layered profile and own history UI"
```

### Task 4: 接入管理端只读展示、跨端契约和发布资料

**Files:**
- Modify: `admin-react/src/pages/SelectionSessionsPage.tsx`
- Modify: `admin-react/tests/technician-workspace.test.ts`
- Create: `docs/contracts/service-reference-v2.md`
- Modify: `docs/TEAM-MEMORY.md`
- Modify: `docs/workstreams/technician.md`
- Modify: `docs/workstreams/admin.md`
- Modify: `docs/CURRENT-STATE.md`
- Modify: `docs/WORK-STATUS.md`

**Interfaces:**
- Consumes: v3 字典、画像记录和本人历史 API。
- Produces: 管理端按门店读取的 v3 摘要、文档化跨端契约与生产事实。

- [ ] **Step 1: 写失败测试**

```ts
test('管理端将 v3 服务参考显示为结构化摘要而非普通运营标签', () => {
  const source = read('src/pages/SelectionSessionsPage.tsx');
  assert.match(source, /schema_version/);
  assert.match(source, /service_reference_v2/);
  assert.doesNotMatch(source, /addUserTag\(/);
});
```

- [ ] **Step 2: 运行失败测试**

Run: `npm test -- --test-name-pattern="v3 服务参考"`

Expected: FAIL，因为管理页尚未识别 v3。

- [ ] **Step 3: 实现管理端最小只读摘要**

在已有顾客画像读取位置渲染 v3 分组摘要、确认状态、记录时间和来源；相关情况原话默认折叠，不将其复制到普通标签或搜索索引。

- [ ] **Step 4: 更新跨端契约和工作状态**

`service-reference-v2.md` 必须列出每一组稳定编码、来源、确认语义、可见范围、禁止自动分析字段和 v1 兼容规则。完成实现后更新 `TEAM-MEMORY.md` 和两个 workstream；实际发布窗口最后更新 `CURRENT-STATE.md` 与 `WORK-STATUS.md` 的备份、迁移、Manifest、健康和移动验收事实。

- [ ] **Step 5: 运行跨端验证**

Run: `pytest hxy-server/tests/test_technician_profile_v3_contract.py hxy-server/tests/test_technician_service_history_api.py -q && cd admin-react && npm test && npm run build`

Expected: 合同、权限、历史与前端测试全绿。

- [ ] **Step 6: 提交**

```bash
git add admin-react/src/pages/SelectionSessionsPage.tsx admin-react/tests/technician-workspace.test.ts docs/contracts/service-reference-v2.md docs/TEAM-MEMORY.md docs/workstreams/technician.md docs/workstreams/admin.md
git commit -m "docs: document customer profile v3 contract"
```

### Task 5: 发布前验证、生产发布和现场验收

**Files:**
- Modify: `docs/CURRENT-STATE.md`
- Modify: `docs/WORK-STATUS.md`

**Interfaces:**
- Consumes: 已通过 CI 的 main commit 与自动发布流程。
- Produces: 已核验生产事实和可追溯现场验收结果。

- [ ] **Step 1: 发布前执行完整回归**

Run: `pytest hxy-server/tests -q && cd admin-react && npm test && npm run build && git diff --check`

Expected: 后端、管理/技师前端和生产构建通过；若出现与本改动无关的既有失败，先定位并在 PR 中明确记录。

- [ ] **Step 2: 创建 PR 并等待必需检查**

PR 描述必须包含：v3 schema/taxonomy、迁移回填边界、本人历史权限边界、未确认记录处理、测试结果和生产风险。合并仅在准确 head SHA 的检查均成功后进行。

- [ ] **Step 3: 按受保护生产流程发布**

合并后等待自动发布：确认数据库备份与恢复演练、Alembic 到新 head、Release Manifest、原子切换、API/DB 容器健康和公网四入口 HTTP 200。

- [ ] **Step 4: 完成 390×844 移动验收**

使用授权脱敏测试账号依次完成：确认服务、结束服务、快速快记、展开项记录、顾客确认、打开本人历史、刷新、重复提交、断网恢复、管理端只读摘要和审计核对。不得用真实顾客信息测试。

- [ ] **Step 5: 记录事实并提交**

在 `CURRENT-STATE.md` 写入实际 release、主干 SHA、迁移、备份、Manifest、健康和验收结论；在 `WORK-STATUS.md` 顶部追加同一批可复核事实。

```bash
git add docs/CURRENT-STATE.md docs/WORK-STATUS.md
git commit -m "docs: record customer profile v3 production release"
```
