# 服务位维修备注与展示顺序 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为店长和总部管理员提供实际服务位的维修备注与展示顺序编辑能力，同时保持门店隔离、普通员工只读和智慧宝物理资源边界。

**Architecture:** `Room.note` 和 `Room.sort_order` 已存在，因此后端在 occupancy 路由新增一个严格的 Pydantic 请求模型和服务位专用 PATCH，将公开字段映射为现有存储字段。管理端在既有服务位详情抽屉中调用该 PATCH；实时地图继续按已有 `sort_order, id` 查询，只需接收并展示备注与顺序。

**Tech Stack:** FastAPI、Pydantic v2、SQLAlchemy、SQLite TestClient、React、TypeScript、Ant Design、node:test。

## Global Constraints

- 仅实际服务位可编辑；空间容器与非服务位拒绝。
- `maintenance_note` 为空字符串时清空，最大 256 字；`display_order` 是不小于 0 的整数。
- 总部管理员和店长可写；普通员工无写入口且后端拒绝；跨店目标返回 404。
- 不变更 `operational_status`、占用、服务单、二维码、顾客扫码、地图布局或智慧宝物理资源。
- 不新增数据库列或 Alembic 迁移；保留旧 `note`、`sort_order` 数据。
- 同一 PR 更新合同测试、`docs/TEAM-MEMORY.md` 和服务位契约文档。

---

### Task 1: 严格服务位配置 API 与后端合同测试

**Files:**
- Modify: `hxy-server/app/api/occupancies.py:391-446`
- Modify: `hxy-server/tests/test_occupancy_api.py`
- Modify: `hxy-server/tests/test_admin_resource_permissions.py`

**Interfaces:**
- Consumes: `Room.note`, `Room.sort_order`, `_current_staff()`, `_staff_store_id()`, `normalize_staff_role()` and `_audit_qr()` audit style in `app/api/occupancies.py`.
- Produces: `PATCH /api/v1/admin/service-positions/{room_id}/configuration` accepting `ServicePositionConfigurationIn`, returning `{ "id": int, "maintenance_note": str, "display_order": int }`.

- [ ] **Step 1: Write failing API-contract tests**

```python
response = self.client.patch(
    f"/api/v1/admin/service-positions/{room.id}/configuration",
    headers=self.admin_headers,
    json={"maintenance_note": "等待维修", "display_order": 3},
)
self.assertEqual(response.status_code, 200, response.text)
self.assertEqual(response.json(), {"id": room.id, "maintenance_note": "等待维修", "display_order": 3})

invalid = self.client.patch(url, headers=self.admin_headers, json={"display_order": -1})
self.assertEqual(invalid.status_code, 422)
```

Add cases for empty payload, unknown `operational_status`, note length 257, a space container, a non-service room, ordinary `staff`, and a room owned by a second store. Verify the persisted fields and the audit payload include before/after values.

- [ ] **Step 2: Run the new tests and verify failure**

Run: `python -m pytest tests/test_occupancy_api.py tests/test_admin_resource_permissions.py -q`

Expected: configuration endpoint tests fail with 404 before the route exists.

- [ ] **Step 3: Add the strict request model and endpoint**

```python
class ServicePositionConfigurationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    maintenance_note: str | None = Field(default=None, max_length=256)
    display_order: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def has_change(self):
        if self.maintenance_note is None and self.display_order is None:
            raise ValueError("至少提交一项服务位配置")
        return self
```

Implement `update_service_position_configuration()` beside the operational-status route. Resolve the logged-in manager's store before selecting `Room`; require `is_service_position` and not `is_space_container`; map only provided fields; write one audit event containing old and new values; commit once and return the normalized public response. Do not call or reuse an operation that changes `operational_status`.

- [ ] **Step 4: Run the backend regression set**

Run: `python -m pytest tests/test_occupancy_api.py tests/test_admin_resource_permissions.py -q`

Expected: PASS; preserve the existing warning only if it is unrelated to this feature.

- [ ] **Step 5: Commit the backend slice**

```bash
git add hxy-server/app/api/occupancies.py hxy-server/tests/test_occupancy_api.py hxy-server/tests/test_admin_resource_permissions.py
git commit -m "feat(admin): configure service positions"
```

### Task 2: 管理端配置请求、权限和详情抽屉

**Files:**
- Modify: `admin-react/src/api.ts:156-176`
- Modify: `admin-react/src/servicePositions.ts:34-63`
- Modify: `admin-react/src/pages/ServicePositionsPage.tsx:1-220, 440-520`
- Create: `admin-react/tests/service-position-configuration.test.ts`

**Interfaces:**
- Consumes: `PATCH /admin/service-positions/{roomId}/configuration` and `canManageConfiguration(role)`.
- Produces: `updateServicePositionConfiguration(roomId, payload)` plus `ServicePosition.maintenance_note` and `ServicePosition.display_order` fields consumed by the detail drawer.

- [ ] **Step 1: Write failing management-page tests**

```ts
test('only configuration managers receive the edit capability', () => {
  assert.equal(canManageServicePositionConfiguration('manager'), true);
  assert.equal(canManageServicePositionConfiguration('staff'), false);
});

test('configuration request maps note and order without operational state', () => {
  assert.deepEqual(buildServicePositionConfigurationPayload('维修中', 4), {
    maintenance_note: '维修中', display_order: 4,
  });
});
```

Add source assertions that the page calls `updateServicePositionConfiguration`, shows “维修备注” and “展示顺序”, and does not add physical-resource action names prohibited by `navigation-boundary.test.ts`.

- [ ] **Step 2: Run the focused frontend test and verify failure**

Run: `npm test -- --run tests/service-position-configuration.test.ts`

Expected: FAIL because the helper/export and page integration do not exist.

- [ ] **Step 3: Implement the smallest typed UI integration**

```ts
export type ServicePositionConfiguration = {
  maintenance_note?: string;
  display_order?: number;
};

export const updateServicePositionConfiguration = (roomId: number, payload: ServicePositionConfiguration) =>
  client.patch(`/admin/service-positions/${roomId}/configuration`, payload);
```

Add `maintenance_note` and `display_order` to the live-map type. In the selected-position detail drawer, conditionally render editable `Input.TextArea` and `InputNumber(min=0, precision=0)` plus a save button for `canManageConfiguration(staff?.role)`. Save only these fields, show the API error through the existing `message` instance, refresh `load(true)` after success, and preserve every existing operational-status/QR action. For non-managers, render no configuration controls and no maintenance note.

- [ ] **Step 4: Run frontend behavior and boundary regression tests**

Run: `npm test -- --run tests/service-position-configuration.test.ts tests/qr-management.test.ts tests/navigation-boundary.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit the frontend slice**

```bash
git add admin-react/src/api.ts admin-react/src/servicePositions.ts admin-react/src/pages/ServicePositionsPage.tsx admin-react/tests/service-position-configuration.test.ts
git commit -m "feat(admin): edit service position configuration"
```

### Task 3: 共享契约、知识同步与最终验证

**Files:**
- Create: `docs/contracts/service-position-configuration-v1.md`
- Modify: `docs/TEAM-MEMORY.md`
- Modify: `docs/workstreams/admin.md`

**Interfaces:**
- Consumes: final endpoint and UI behavior from Tasks 1–2.
- Produces: one authoritative contract that documents fields, permissions, response/error behavior, and physical-resource boundary.

- [ ] **Step 1: Write the contract and memory facts**

Document the exact endpoint, request fields, 256-character and non-negative validation, mapping to existing Room fields, manager/store isolation, staff denial, 404 cross-store behavior, audit requirement, no migration, and all non-goals. Update `TEAM-MEMORY.md` and the admin workstream with only facts verified by tests; do not claim PR merge, production deployment, or field acceptance.

- [ ] **Step 2: Verify documentation contains no unresolved placeholders**

Run: `rg -n -i 'unresolved-marker' docs/contracts/service-position-configuration-v1.md docs/TEAM-MEMORY.md docs/workstreams/admin.md`

Expected: no result attributable to this feature.

- [ ] **Step 3: Run final local verification**

Run:

```bash
cd hxy-server && python -m pytest tests/test_occupancy_api.py tests/test_admin_resource_permissions.py -q
cd ../admin-react && npm test -- --run
npx tsc -b
cd .. && git diff --check
```

Expected: targeted backend tests, frontend suite, type check, and whitespace validation pass.

- [ ] **Step 4: Commit the contract and documentation**

```bash
git add docs/contracts/service-position-configuration-v1.md docs/TEAM-MEMORY.md docs/workstreams/admin.md
git commit -m "docs(admin): record service position configuration contract"
```

- [ ] **Step 5: Prepare PR automation handoff**

Push `codex/admin/service-position-config`, create a PR against `main`, record its full head SHA, then start `tools/release/start-release-watch.ps1` with `-Merge` under the standing user authorization. Report only the script PID and report path while it waits; read the report once on the next status request.
