# DIY 管理后台结构化重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保留现有 React/Vite + Ant Design 和既有业务状态机的前提下，完成 DIY 管理后台的角色、门店隔离、业务边界、资源化前端和技师工作台改造，并达到可验证的生产切换门禁。

**Architecture:** 后端先建立显式的 manager/technician 权限与当前门店上下文，再补齐所有资源查询的 store_id 条件；前端保留现有路由技术栈，以 core/auth、core/dataProvider、resources 和 features 分层，状态流页面继续使用自定义 Ant Design。生产发布仅在全部测试、数据库恢复演练、Manifest 校验和公网健康检查通过后由管理后台窗口执行。

**Tech Stack:** Python/FastAPI/SQLAlchemy/Alembic/pytest；React/TypeScript/Vite/Ant Design/HashRouter；PostgreSQL；现有部署脚本和 release 目录。

## Global Constraints

- 只支持当前门店操作，所有用户、会员、标签、订单、服务、事件、优惠券、配置和审计数据必须按 `store_id` 隔离。
- `manager` 表示管理员/店长；`technician` 表示技师；不新增前台、财务、预约或派单角色。
- 智慧宝负责开位、开房、派钟、离位、清洁和物理资源释放；DIY 只负责电子菜单、服务确认、服务结束、评价、画像和审计。
- DIY 后台不得展示或调用预约、派单、房间绑定技师、确认离位、完成清洁和普通物理释放动作。
- 不做 Refine 全量迁移；可吸收其资源、data provider、权限和页面分层思想。
- 每个代码改动必须有对应测试；未完成全量测试、数据库备份/恢复演练、Manifest 校验和线上健康检查，不得声称生产可用。
- 不回滚、覆盖或清理工作区中已有未提交改动。

---

### Task 1: 角色迁移、技师绑定与权限矩阵

**Files:**
- Modify: `hxy-server/app/models/core.py`（`Staff.role`、`technician_id` 约束）
- Modify: `hxy-server/app/models/operations.py`（技师关系）
- Modify: `hxy-server/app/api/auth.py`、`hxy-server/app/api/admin_v2.py`、相关依赖注入文件
- Create: `hxy-server/alembic/versions/<timestamp>_normalize_staff_roles.py`
- Create: `hxy-server/tests/test_staff_role_migration.py`
- Modify: `hxy-server/tests/test_admin_resource_permissions.py`

**Interfaces:**
- 统一当前员工对象返回 `role: Literal["manager", "technician"]`、`store_id` 和可选 `technician_id`。
- 兼容读取历史 `admin/staff`，映射为 `manager/technician`；历史审计中的原值不修改。
- 技师写画像/服务记录时从认证上下文取得 `technician_id`，请求体不得覆盖；店长代录必须写入代录审计。

- [ ] **Step 1: 写迁移失败测试**：覆盖 `admin -> manager`、已绑定 `staff -> technician`、未绑定 `staff` 被拒绝、重复技师绑定被拒绝，以及旧审计角色仍可展示。
- [ ] **Step 2: 运行失败测试**：`pytest tests/test_staff_role_migration.py tests/test_admin_resource_permissions.py -q`，确认新契约尚未满足。
- [ ] **Step 3: 实现迁移和依赖**：增加可回滚 Alembic 迁移、账号盘点脚本输出未绑定账号；新增 `require_manager`、`require_technician` 和 `current_store_context`，逐 endpoint 使用权限矩阵。
- [ ] **Step 4: 验证通过**：同一测试命令必须 PASS，并补充 401/403 响应结构断言。
- [ ] **Step 5: 提交**：`git add hxy-server/app hxy-server/alembic hxy-server/tests && git commit -m "feat: normalize admin and technician roles"`。

### Task 2: 全面门店隔离和优惠券归属

**Files:**
- Modify: `hxy-server/app/api/admin.py`（行为分析、热门项目）
- Modify: `hxy-server/app/api/admin_v2.py`、`hxy-server/app/api/marketing.py`
- Modify: `hxy-server/app/models/marketing.py`（`CouponTemplate.store_id`）
- Create: `hxy-server/alembic/versions/<timestamp>_scope_coupon_templates_to_store.py`
- Create: `hxy-server/tests/test_store_isolation_regressions.py`
- Modify: `hxy-server/tests/test_admin_stats_store_scope.py`、`test_admin_audit_store_scope.py`、`test_admin_scrm_store_scope.py`

**Interfaces:**
- 每个管理 API 从认证员工上下文取得门店，不接受客户端任意 `store_id` 覆盖。
- 跨店对象读取、更新、删除统一返回 404（避免泄露存在性）；跨店统计不计入结果。

- [ ] **Step 1: 写跨店失败测试**：行为分析 EventLog、热门项目、优惠券列表/新增/更新、顾客画像、订单和审计各建立两个门店夹具，断言只能看到当前门店。
- [ ] **Step 2: 运行失败测试**：`pytest tests/test_store_isolation_regressions.py tests/test_admin_stats_store_scope.py tests/test_admin_audit_store_scope.py tests/test_admin_scrm_store_scope.py -q`。
- [ ] **Step 3: 实现查询条件和迁移**：为缺失模型补 `store_id`、索引和非空回填；所有 CRUD 使用 `(id, current_store_id)` 条件；热门项目通过本店订单/选单关联读取。
- [ ] **Step 4: 验证通过**：运行同一测试集合，并执行 `python scripts/inspect_schema_drift.py` 检查迁移与模型一致。
- [ ] **Step 5: 提交**：`git add hxy-server/app hxy-server/alembic hxy-server/tests && git commit -m "fix: enforce store isolation across admin resources"`。

### Task 3: 清除预约/派单残留并落实智慧宝边界

**Files:**
- Modify: `admin-react/src/layouts/MainLayout.tsx`、`src/App.tsx`（删除 reservations 路由/菜单和 today-appointments 默认入口）
- Modify: `admin-react/src/pages/RoomsPage.tsx`（移除 `createAssignment` 和技师绑定操作）
- Modify: `admin-react/src/pages/TodayPage.tsx`、`ServicePositionsPage.tsx`、`operations.ts`
- Create: `admin-react/src/__tests__/navigation-boundary.test.tsx`
- Modify: `hxy-server/tests/test_business_closure_state_machine.py`、`test_occupancy_api.py`

**Interfaces:**
- DIY 服务位普通动作仅暴露“确认服务”“服务结束”；物理离位、清洁、释放、派单动作不在新管理端调用。
- 后端保留旧兼容 endpoint 时必须由明确的 legacy 标记隔离，不得被新 UI 引用。

- [ ] **Step 1: 写导航和 API 边界失败测试**：渲染 manager/technician 菜单，断言无预约/派单文案；静态扫描禁止 `createAssignment`、`today-appointments` 新调用；服务结束状态机保留电子闭环。
- [ ] **Step 2: 运行失败测试**：`npm test -- --run src/__tests__/navigation-boundary.test.tsx` 和后端边界测试。
- [ ] **Step 3: 实现菜单、路由和动作清理**：删除页面入口与调用，保留历史文件但不被路由加载；把结算/异常动作与智慧宝物理事实分离并写审计。
- [ ] **Step 4: 验证通过**：前端测试、`pytest tests/test_business_closure_state_machine.py tests/test_occupancy_api.py -q`，并用 `rg "reservations|createAssignment|today-appointments|完成清洁|确认离位" admin-react/src` 确认无新入口。
- [ ] **Step 5: 提交**：`git add admin-react hxy-server/tests && git commit -m "refactor: align DIY admin with physical operations boundary"`。

### Task 4: 管理端 core/dataProvider/resources 分层

**Files:**
- Create: `admin-react/src/core/auth/index.ts`、`permissions.ts`、`storeContext.ts`
- Create: `admin-react/src/core/dataProvider/index.ts`、`errors.ts`、`queryKeys.ts`
- Create: `admin-react/src/core/resources/index.ts`
- Modify: `admin-react/src/api.ts`、`src/auth.ts`、`src/main.tsx`
- Create: `admin-react/src/__tests__/dataProvider.test.ts`

**Interfaces:**
- `dataProvider.getList<T>(resource, params)`、`getOne<T>(resource, id)`、`create<TInput,T>(resource, input, idempotencyKey?)`、`update<TInput,T>(resource,id,input,version?)`、`remove(resource,id)`。
- 统一处理缓存键、失效、401 跳转登录、403 权限提示、409 版本冲突和 `X-Idempotency-Key`。

- [ ] **Step 1: 写失败测试**：mock fetch，覆盖 query key 稳定性、401/403/409 归一化、创建幂等键、更新版本冲突和 store_id 不可由输入覆盖。
- [ ] **Step 2: 运行失败测试**：`npm test -- --run src/__tests__/dataProvider.test.ts`。
- [ ] **Step 3: 实现 provider 和 auth/store context**：以现有 axios/base URL 为底层，逐步适配 `api.ts`，不引入全量 Refine 依赖。
- [ ] **Step 4: 接入一个样板资源**：先将服务单列表迁移到 provider，保留行为一致并增加加载/错误/重试反馈。
- [ ] **Step 5: 验证并提交**：`npm test -- --run src/__tests__/dataProvider.test.ts`、`npm run build`；提交 `feat: add resource data provider foundation`。

### Task 5: 技师服务单和顾客画像工作台

**Files:**
- Modify: `hxy-server/app/api/admin_v2.py`（服务单列表、画像记录）
- Create: `hxy-server/app/schemas/profile.py`
- Create: `hxy-server/tests/test_technician_service_scope.py`、`test_profile_record_contract.py`
- Modify: `admin-react/src/pages/TechnicianHomePage.tsx`、`UsersPage.tsx`
- Create: `admin-react/src/features/technician/ServiceOrderList.tsx`、`ProfileRecordForm.tsx`

**Interfaces:**
- 技师服务单列表参数：`status=in_progress|history`、`page`、`page_size<=100`；响应按本店分页并对手机号、价格和会员字段脱敏。
- `POST /admin/v2/customers/{id}/profile-records` 只接收 `tags[]`、`service_note`（长度限制、非诊断词校验）；技师身份由 token 注入。

- [ ] **Step 1: 写失败测试**：技师只能看本店服务单、默认进行中；不能改价/结算/释放；不能伪造 `technician_id`；非法健康诊断词和超长文本被拒绝；店长代录有审计。
- [ ] **Step 2: 运行失败测试**：`pytest tests/test_technician_service_scope.py tests/test_profile_record_contract.py -q`。
- [ ] **Step 3: 实现 schema、endpoint 和页面**：定义允许字段、可见角色和脱敏函数；工作台使用 provider，支持历史筛选和新增记录/更正链。
- [ ] **Step 4: 验证通过**：后端测试、前端组件测试和 TypeScript 构建。
- [ ] **Step 5: 提交**：`git add hxy-server admin-react && git commit -m "feat: add technician service and profile workspace"`。

### Task 6: 店长运营页面、资源和内容页面收口

**Files:**
- Modify: `admin-react/src/layouts/MainLayout.tsx`（最终菜单与角色可见性）
- Modify: `admin-react/src/pages/TodayPage.tsx`、`OrdersPage.tsx`、`FeedbackPage.tsx`、`AnalyticsPage.tsx`、`CouponsPage.tsx`、`RoomsPage.tsx`、`ProjectsPage.tsx`、`UsersPage.tsx`
- Create: `admin-react/src/features/operations/index.ts`、`catalog/index.ts`、`customers/index.ts`、`resources/index.ts`
- Create: `admin-react/src/__tests__/role-menu.test.tsx`、`store-context-ui.test.tsx`

**Interfaces:**
- manager 可见经营、服务位、服务单、结算异常、顾客画像、项目价格、资源二维码、会员顾客、营销内容和审计；technician 仅可见服务单、顾客画像和个人账号退出。
- 当前单店不显示 `/stores` 主数据页和切店器。

- [ ] **Step 1: 写角色菜单失败测试**：分别渲染两角色，断言菜单集合、禁止路由跳转和当前门店标签。
- [ ] **Step 2: 运行失败测试**：`npm test -- --run src/__tests__/role-menu.test.tsx src/__tests__/store-context-ui.test.tsx`。
- [ ] **Step 3: 实现页面收口**：将重复请求改为 provider/resource；服务位看板固定 8 沙发+9 床位；房间只作容器分组；所有列表显示门店上下文和审计入口。
- [ ] **Step 4: 验证通过**：运行管理端全量测试和 `npm run build`。
- [ ] **Step 5: 提交**：`git add admin-react && git commit -m "feat: finalize DIY manager operations information architecture"`。

### Task 7: 综合验证、发布门禁与文档

**Files:**
- Modify: `docs/WORK-STATUS.md`
- Modify: `hxy-server/docs/superpowers/specs/2026-08-26-diy-admin-structured-refactor-design.md`（勾选已落地项）
- Use: `hxy-server/scripts/rehearse_postgres_restore.py`、`check_release_consistency.py`、部署脚本
- Create: `hxy-server/tests/test_release_gates.py`

**Interfaces:**
- 发布门禁输出：测试摘要、数据库备份与恢复演练路径、Manifest 校验结果、服务器 `current` readlink、健康检查 URL 和现场验收清单。

- [ ] **Step 1: 写门禁测试**：缺任一测试、备份、Manifest 或健康检查结果时，发布检查必须失败。
- [ ] **Step 2: 运行管理端和后端全量测试**：后端 `pytest -q`；管理端 `npm test -- --run`、`npm run build`。
- [ ] **Step 3: 执行服务器只读核验**：确认生产 `current` 指向实际 release；运行 schema drift、Manifest、健康检查和恢复演练，记录命令输出。
- [ ] **Step 4: 更新状态文档**：记录修改内容、文件、测试结果、是否发布、生产 release、待现场验收事项；未发布前明确“本地完成/待服务器验证”。
- [ ] **Step 5: 仅由管理后台窗口发布**：完成审批和现场验收后再切换 release；发布后重新 readlink 并做公网回归，提交 `chore: record release gates and production verification`。

## 自审清单

- 角色迁移、技师绑定、逐 endpoint 权限和审计均有 Task 1/5 覆盖。
- 所有已知串店点（EventLog、热门项目、优惠券）及通用资源隔离有 Task 2 覆盖。
- 预约、派单、物理离位/清洁/释放残留有 Task 3 覆盖。
- dataProvider 的缓存、幂等、401/403/409、版本冲突有 Task 4 覆盖。
- 响应式菜单、店长/技师差异、17 个服务位和单店隐藏 stores 有 Task 6 覆盖。
- 测试、备份恢复、Manifest、health check、生产 current 和现场验收有 Task 7 覆盖。

