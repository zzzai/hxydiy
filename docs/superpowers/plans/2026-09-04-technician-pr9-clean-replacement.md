# 技师端 PR #9 干净替代实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在最新 `origin/main` 上重建 PR #9 的技师端可靠性与账号状态修正，避免旧 PR 回退或删除后续主线能力。

**Architecture:** 保留主线现有管理端、顾客端、媒体与 CI 实现，只修改技师门户 API、技师移动页面及对应回归测试。服务端负责账号资格、门店/状态机、冲突服务位和幂等约束；前端只呈现服务端返回的安全状态。

**Tech Stack:** FastAPI、SQLAlchemy、pytest、React、TypeScript、Node test、Vite

## Global Constraints

- 只处理技师账号、技师移动工作台和技师相关后端，不加入派单、结算、智慧宝物理资源操作、顾客端或桌面管理后台改造。
- 所有写操作继续由服务端校验角色、门店、状态、幂等与审计。
- 工作分支从最新 `origin/main` 创建，不强推、不直接修改 `main`。
- 生产发布仅在 PR 合并且主线 CI 成功后评估；本计划不直接发布生产。

---

### Task 1: 技师门户服务端可靠性

**Files:**
- Modify: `hxy-server/app/api/technician.py`
- Modify: `hxy-server/app/api/technician_admin.py`
- Test: `hxy-server/tests/test_technician_portal_api.py`
- Test: `hxy-server/tests/test_technician_account_lifecycle.py`

**Interfaces:**
- Consumes: `Staff.status`、`Technician.status`、`PositionOccupancy`、`StateTransition`
- Produces: `TECHNICIAN_ACCOUNT_UNAVAILABLE`、`POSITION_OCCUPANCY_CONFLICT`、`TECHNICIAN_ACTIVE_SERVICE`、`IDEMPOTENCY_KEY_REUSED`，以及 `/technician/me` 中分离的账号与服务状态

- [ ] **Step 1: 写入旧 PR 中的服务端失败回归测试**
- [ ] **Step 2: 运行两个技师专项文件，确认测试因主线缺少对应行为而失败**
- [ ] **Step 3: 最小移植 `d6808ef` 的服务端实现，不修改无关 API**
- [ ] **Step 4: 重跑两个专项文件并确认通过**

### Task 2: 技师移动端冲突与状态展示

**Files:**
- Modify: `admin-react/src/technician/TechnicianTodayPage.tsx`
- Modify: `admin-react/src/technician/TechnicianMePage.tsx`
- Modify: `admin-react/src/technician/technicianMobile.ts`
- Modify: `admin-react/src/technician/technician-mobile.css`
- Test: `admin-react/tests/technician-mobile.test.ts`
- Test: `admin-react/tests/technician-workspace.test.ts`

**Interfaces:**
- Consumes: `/api/v1/technician/tasks` 的 `conflict/conflict_count` 与 `/api/v1/technician/me` 的 `staff.status`、`technician.status`
- Produces: “待核对”冲突卡片、禁用服务操作、账号状态与服务状态分别展示

- [ ] **Step 1: 写入旧 PR 中的前端失败回归测试**
- [ ] **Step 2: 运行两个测试文件，确认缺少映射和冲突展示时失败**
- [ ] **Step 3: 最小移植 `d6808ef`、`3804fe0` 的前端实现**
- [ ] **Step 4: 重跑专项测试、全量 `npm test`、`npx tsc --noEmit` 与 `npm run build`**

### Task 3: PR 门禁与文档交付

**Files:**
- Modify: `docs/workstreams/technician.md`
- Modify: `docs/WORK-STATUS.md`
- Modify when contract facts change: `docs/TEAM-MEMORY.md`

**Interfaces:**
- Consumes: 本地测试、GitHub Checks、服务器 `current` 与健康探针证据
- Produces: 可审计的本地/PR/生产/现场验收状态记录

- [ ] **Step 1: 运行交付提示词列出的技师/画像后端专项测试**
- [ ] **Step 2: 运行 `git diff --check` 并审查相对 `origin/main` 的文件范围**
- [ ] **Step 3: 更新共享状态文档，明确生产 current 与 Manifest 实时核验结果**
- [ ] **Step 4: 提交并推送干净替代分支，创建目标为 `main` 的非 Draft PR**
- [ ] **Step 5: 等待并读取六项检查；失败则按日志补回归测试后修复**
