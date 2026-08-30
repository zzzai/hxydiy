# 技师账号生命周期 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline execution in this session).

**Goal:** 为内部技师提供“账号 + 密码 + 店长重置”的手机端账号生命周期，并确保 Staff 登录身份与 Technician 业务档案分离、门店隔离、旧会话即时失效和全链路审计。

**Architecture:** 在现有 FastAPI + SQLAlchemy 身份模型上增加 Staff 凭证版本和 TechnicianInvite 用途字段；JWT 携带凭证版本并由服务端校验。店长通过 `/admin/v2/technicians/{id}/...` 管理开通、重置、停用、恢复、离职和返聘，技师通过 `/technician/activate` 首次激活或重置密码；React 管理端显示账号状态和一次性凭证，手机端提供激活表单。

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, PostgreSQL/SQLite tests, React 18, TypeScript, Ant Design, Node test runner, Vite。

## Global Constraints

- 技师端为手机优先 Web，入口为 `/technician/`；桌面管理后台不作为技师日常入口。
- 技师不开放公众注册；首次激活和忘记密码均由店长生成一次性凭证。
- Staff 是登录身份，Technician 是业务档案，通过 `Staff.technician_id` 关联，不合并对象。
- 停用和离职撤销登录能力，但保留技师档案、服务单、顾客服务参考和审计；不物理删除。
- 不新增智慧宝负责的开房、开沙发、派单、离位、清洁或物理资源释放能力。
- 所有写接口必须服务端校验店长角色、当前门店、目标对象关联，支持幂等或等价状态幂等并写审计。
- 密码只保存 PBKDF2 哈希；激活凭证只保存 SHA-256 哈希，明文只在店长成功响应展示一次。
- 顾客画像文案使用“顾客自述/服务观察/服务注意事项”，不使用医疗诊断式表述。
- 修改业务代码前必须先新增失败测试并确认按预期失败；每个任务独立运行覆盖测试。
- 发布前必须读取服务器实际 `current`，完成数据库备份、迁移 head 校验、Manifest 校验、原子切换和线上健康检查。

---

### Task 1: 凭证版本与邀请用途数据模型

**Files:**
- Create: `C:/Users/gaoji/WorkBuddy/2026-07-31-12-31-02/hxy-server/alembic/versions/20260828_technician_account_lifecycle.py`
- Modify: `C:/Users/gaoji/WorkBuddy/2026-07-31-12-31-02/hxy-server/app/models/core.py`
- Modify: `C:/Users/gaoji/WorkBuddy/2026-07-31-12-31-02/hxy-server/app/models/technician_portal.py`
- Test: `C:/Users/gaoji/WorkBuddy/2026-07-31-12-31-02/hxy-server/tests/test_technician_account_lifecycle.py`

**Interfaces:**
- Produces `Staff.credentials_version: int` defaulting to `1` and `TechnicianInvite.purpose: str` with `activate`/`reset` values.
- Migration must be safely repeatable on SQLite and PostgreSQL and must point to the current tracked technician portal/role migration chain without deleting existing rows.

- [ ] **Step 1: Write the failing test**

```python
def test_account_columns_have_safe_defaults_and_invite_purpose_is_required():
    with SessionLocal() as db:
        staff = db.get(Staff, staff_id)
        invite = TechnicianInvite(
            store_id=store_id, technician_id=technician_id, staff_id=staff.id,
            token_hash="a" * 64, purpose="activate",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            created_by_staff_id=staff.id,
        )
        db.add(invite); db.commit(); db.refresh(staff)
        assert staff.credentials_version == 1
        assert invite.purpose == "activate"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_technician_account_lifecycle.py::test_account_columns_have_safe_defaults_and_invite_purpose_is_required -q`

Expected: FAIL because the model columns do not exist.

- [ ] **Step 3: Write minimal implementation**

Add the two mapped columns and an idempotent Alembic migration. Existing invite rows receive `purpose='activate'`; do not change passwords, staff status, or historical audit rows.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_technician_account_lifecycle.py::test_account_columns_have_safe_defaults_and_invite_purpose_is_required -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/models/core.py app/models/technician_portal.py alembic/versions/20260828_technician_account_lifecycle.py tests/test_technician_account_lifecycle.py
git commit -m "feat: add technician credential lifecycle fields"
```

### Task 2: JWT 版本校验与登录/激活生命周期接口

**Files:**
- Modify: `C:/Users/gaoji/WorkBuddy/2026-07-31-12-31-02/hxy-server/app/api/admin.py`
- Modify: `C:/Users/gaoji/WorkBuddy/2026-07-31-12-31-02/hxy-server/app/api/technician.py`
- Test: `C:/Users/gaoji/WorkBuddy/2026-07-31-12-31-02/hxy-server/tests/test_technician_account_lifecycle.py`

**Interfaces:**
- `create_staff_token(staff_id, role, credentials_version=1)` signs `credentials_version`.
- `_current_staff` rejects a token whose version differs from the stored Staff version with `STAFF_SESSION_REVOKED`.
- `/api/v1/admin/login` signs the stored version and keeps manager/staff login compatibility.
- `/api/v1/technician/activate` accepts invite purpose `activate` or `reset`, sets the new password, increments version for reset, consumes the invite once, and returns a technician token.

- [ ] **Step 1: Write the failing tests**

```python
def test_reset_or_disable_invalidates_an_existing_jwt():
    old_token = create_staff_token(staff_id, "technician", credentials_version=1)
    with SessionLocal() as db:
        db.get(Staff, staff_id).credentials_version = 2; db.commit()
    response = client.get("/api/v1/technician/me", headers={"Authorization": f"Bearer {old_token}"})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "STAFF_SESSION_REVOKED"

def test_activation_invite_is_single_use_and_reset_purpose_requires_new_password():
    invite = issue_invite(purpose="reset")
    activated = client.post("/api/v1/technician/activate", json={"token": invite, "password": "new-pass-123"})
    assert activated.status_code == 200
    replay = client.post("/api/v1/technician/activate", json={"token": invite, "password": "other-pass-123"})
    assert replay.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_technician_account_lifecycle.py::test_reset_or_disable_invalidates_an_existing_jwt tests/test_technician_account_lifecycle.py::test_activation_invite_is_single_use_and_reset_purpose_requires_new_password -q`

Expected: FAIL because JWT has no version and reset-purpose behavior is absent.

- [ ] **Step 3: Write minimal implementation**

Thread the version through token creation and `_current_staff`; centralize invite validation so expired, used, cross-store, and inconsistent records return the same non-disclosing activation error. Preserve current service action boundaries.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_technician_account_lifecycle.py tests/test_auth_boundary_p0.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/admin.py app/api/technician.py tests/test_technician_account_lifecycle.py
git commit -m "feat: revoke technician sessions by credential version"
```

### Task 3: 店长管理接口与审计/状态幂等

**Files:**
- Modify: `C:/Users/gaoji/WorkBuddy/2026-07-31-12-31-02/hxy-server/app/api/technician_admin.py`
- Modify: `C:/Users/gaoji/WorkBuddy/2026-07-31-12-31-02/hxy-server/app/api/admin_v2.py`
- Test: `C:/Users/gaoji/WorkBuddy/2026-07-31-12-31-02/hxy-server/tests/test_technician_account_lifecycle.py`
- Test: `C:/Users/gaoji/WorkBuddy/2026-07-31-12-31-02/hxy-server/tests/test_technician_portal_api.py`

**Interfaces:**
- `POST /api/v1/admin/v2/technicians/{id}/invite`
- `POST /api/v1/admin/v2/technicians/{id}/reset-login`
- `POST /api/v1/admin/v2/technicians/{id}/disable`
- `POST /api/v1/admin/v2/technicians/{id}/restore`
- `POST /api/v1/admin/v2/technicians/{id}/resign`
- `POST /api/v1/admin/v2/technicians/{id}/rehire`
- `GET /api/v1/admin/v2/technicians` includes `login_status`, `username`, `credentials_version`, and last lifecycle timestamp without exposing hashes/tokens.

- [ ] **Step 1: Write failing tests**

Cover manager-only and same-store checks, no duplicate Staff on repeated invite, reset revokes old password/JWT, disable/restore idempotency, resign rejection with `assigned`/`ready`/`in_service`, rehire issuing a fresh activation invite, and one audit per actual state transition.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_technician_account_lifecycle.py -q`

Expected: FAIL with 404 for missing endpoints or missing lifecycle fields.

- [ ] **Step 3: Write minimal implementation**

Use `require_admin`/`_current_staff` and explicit `technician.store_id == admin.store_id`; treat cross-store targets as 404. Add a transaction-local state transition/idempotency helper keyed by store, target, action, and request key. Increment `credentials_version` on invite/reset/disable/restore/resign/rehire as specified. Keep resign blocked while active assignments exist; never delete records.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_technician_account_lifecycle.py tests/test_technician_portal_api.py tests/test_technician_service_scope.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/technician_admin.py app/api/admin_v2.py tests/test_technician_account_lifecycle.py tests/test_technician_portal_api.py
git commit -m "feat: manage technician login lifecycle"
```

### Task 4: 管理端账号状态与生命周期操作

**Files:**
- Modify: `C:/Users/gaoji/WorkBuddy/2026-07-31-12-31-02/admin-react/src/api.ts`
- Modify: `C:/Users/gaoji/WorkBuddy/2026-07-31-12-31-02/admin-react/src/pages/TechsPage.tsx`
- Test: `C:/Users/gaoji/WorkBuddy/2026-07-31-12-31-02/admin-react/tests/technician-account-lifecycle.test.ts`

**Interfaces:**
- API helpers `resetTechnicianLogin`, `disableTechnicianLogin`, `restoreTechnicianLogin`, `rehireTechnician` post to the matching endpoints.
- Tech list removes physical delete and renders business status plus login status; lifecycle actions use confirmation and display the one-time credential only in the success modal.

- [ ] **Step 1: Write failing tests**

Assert API helper paths/payloads, status labels for `未开通/待激活/正常/停用/离职`, no delete action, and that the credential modal text says “仅显示一次” without rendering a password field.

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test -- tests/technician-account-lifecycle.test.ts`

Expected: FAIL because helpers and lifecycle UI are absent.

- [ ] **Step 3: Write minimal implementation**

Add helpers and replace the destructive delete action with a lifecycle dropdown. Keep manager permission gating from `canManageConfiguration`; surface structured server error messages and refresh the list after successful operations.

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test -- tests/technician-account-lifecycle.test.ts tests/navigation-boundary.test.ts tests/technician-mobile.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/api.ts src/pages/TechsPage.tsx tests/technician-account-lifecycle.test.ts
git commit -m "feat: add technician account lifecycle controls"
```

### Task 5: 手机端首次激活与失效提示

**Files:**
- Modify: `C:/Users/gaoji/WorkBuddy/2026-07-31-12-31-02/admin-react/src/technician/TechnicianMobileLoginPage.tsx`
- Modify: `C:/Users/gaoji/WorkBuddy/2026-07-31-12-31-02/admin-react/src/technician/TechnicianMobileApp.tsx`
- Modify: `C:/Users/gaoji/WorkBuddy/2026-07-31-12-31-02/admin-react/src/technician/technician-mobile.css`
- Test: `C:/Users/gaoji/WorkBuddy/2026-07-31-12-31-02/admin-react/tests/technician-account-lifecycle.test.ts`

**Interfaces:**
- Login page exposes `首次激活/重置密码` mode with token, new password, and confirmation fields.
- Activation success stores the returned technician token and enters `/technician/today`; invalid/expired/disabled errors retain form values and tell the user to contact the store manager.

- [ ] **Step 1: Write failing tests**

Assert activation request payload, password mismatch validation, login redirect for invited accounts, and local token cleanup on revoked-session response.

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test -- tests/technician-account-lifecycle.test.ts`

Expected: FAIL because activation mode is not rendered and no activation API helper exists.

- [ ] **Step 3: Write minimal implementation**

Add `activateTechnician` API helper and a two-mode mobile form. Do not add SMS, public registration, desktop technician navigation, or management actions to the mobile app.

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test -- tests/technician-account-lifecycle.test.ts tests/technician-mobile.test.ts tests/navigation-boundary.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/api.ts src/technician/TechnicianMobileLoginPage.tsx src/technician/TechnicianMobileApp.tsx src/technician/technician-mobile.css tests/technician-account-lifecycle.test.ts
git commit -m "feat: add mobile technician activation flow"
```

### Task 6: 集成测试、迁移契约和发布门禁

**Files:**
- Modify: `C:/Users/gaoji/WorkBuddy/2026-07-31-12-31-02/hxy-server/tests/test_alembic_contract.py`
- Modify: `C:/Users/gaoji/Documents/ChatGPT/hxy-diy/docs/WORK-STATUS.md`
- Create if needed: `C:/Users/gaoji/WorkBuddy/2026-07-31-12-31-02/hxy-server/alembic/versions/<merge migration>.py`

- [ ] **Step 1: Add the complete-chain regression test**

Run the authorized test fixture through `店长开通 -> 技师激活 -> 手机登录 -> 查看任务 -> 确认服务 -> 服务结束 -> 顾客服务参考`, then `店长重置 -> 旧会话拒绝 -> 新凭证激活 -> 新密码登录`; assert audit rows and store isolation.

- [ ] **Step 2: Verify migration heads fail before merge is added**

Run: `alembic heads`

Expected current development tree may show multiple heads; do not publish until one intentional head or a documented merge migration is present.

- [ ] **Step 3: Implement merge migration and contract checks**

Use the actual current heads returned by `alembic heads`, preserve every branch, and verify `alembic upgrade head` plus downgrade/re-upgrade on a disposable database.

- [ ] **Step 4: Run required local verification**

Run:

```bash
python -m pytest tests/test_technician_account_lifecycle.py tests/test_technician_portal_api.py tests/test_technician_service_scope.py tests/test_auth_boundary_p0.py tests/test_alembic_contract.py -q
cd ../admin-react
npm test
npm run build
```

Expected: all targeted backend/frontend tests pass and the management build succeeds; unrelated pre-existing failures must be recorded, not hidden.

- [ ] **Step 5: Production release gate**

Read server `current` and Manifest; back up the database; stage a versioned release from that exact current plus verified artifacts; validate Manifest, migration heads, API health, `/technician/` and login/activation negative cases; atomically switch current and verify container restart count and rollback path.

- [ ] **Step 6: Update work status**

Record local completion, files, test results, publication status, exact release path/Manifest, and remaining store现场验收 items in `docs/WORK-STATUS.md`. Explicitly distinguish 本地完成、已发布生产、待门店现场验收.

