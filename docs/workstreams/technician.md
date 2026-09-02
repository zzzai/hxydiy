# 技师端工作流

## 负责范围

- 技师登录、首次激活、密码重置、停用、离职和返聘。
- 手机优先的技师今日服务看板、服务记录和个人状态。
- 沙发、房间区位展示；当前门店 8 个沙发、7 个房间，房间不拆分床位。
- 顾客提交后的服务单查看、项目摘要和局部项目部位展示。
- 仅执行“确认服务”和“服务结束”。
- 服务完成后的顾客服务参考快记、幂等写入和审计。
- Staff/Technician 关联、技师角色权限、门店隔离和审计。

## 明确不做

- 派单、接单、认领、换技师或排班。
- 智慧宝开房、开沙发、派钟、离位、清洁和物理资源释放。
- 跨门店顾客搜索、顾客联系方式和无关经营数据。
- 结算、改价、会员操作和经营分析。

## 主要代码目录

- `hxy-server/app/api/technician.py`
- `hxy-server/app/api/technician_admin.py`
- `hxy-server/app/models`
- `hxy-server/alembic`
- `hxy-server/tests`
- `admin-react/src/technician`
- `admin-react/tests`

## 当前已确认状态

- 技师移动端生产入口为 `/technician/`，不进入桌面管理后台。
- 今日页按“沙发”“房间”分组展示全部服务位；空闲、待服务、服务中、已完成使用不同状态色。
- 点击有订单的区位可查看服务单和顾客选单；服务完成后可打开服务参考快记。
- 技师服务参考写入已具备本人完成服务关联、门店校验、字段白名单、医疗诊断词拦截、幂等和审计。
- 已完成线上手机验收：390x844 视口可查看 8 个沙发、7 个房间，点击 3 号沙发可查看服务单 #325；页面底部导航未遮挡最后一个房间卡片。

## 开始任务前检查

1. 读取 `docs/PROJECT-CONTEXT-20260826.md`、`docs/WORK-STATUS.md`、`docs/TEAM-MEMORY.md`。
2. 读取本文件和当前项目 `AGENTS.md`（如果存在）。
3. 检查当前源码、未提交变更、最近生产 release 和服务器实际 `current`。
4. 先补失败测试，再修改实现。
5. 涉及生产时执行数据库备份、Manifest 校验、健康检查和关键链路验收。

## 完成任务后记录

在本文件追加：

- 修改内容
- 涉及文件
- 测试结果
- 是否发布及生产 release
- 风险和待门店现场验收事项

同时更新 `docs/WORK-STATUS.md`，不得只在聊天中报告结果。

## 2026-08-30 技师服务动作幂等键作用域修复（本地完成，未发布）

### 修改内容

- 服务确认/结束接口的幂等键现在绑定当前服务位、动作和登录技师。
- 同一幂等键被用于其他服务位、其他动作或其他技师时返回 `409 IDEMPOTENCY_KEY_REUSED`，不再错误重放首笔结果。
- 保留服务端状态、角色、门店范围、幂等和审计校验；未加入派单或智慧宝物理资源操作。

### 涉及文件

- `hxy-server/app/api/technician.py`
- `hxy-server/tests/test_technician_portal_api.py`
- `docs/TEAM-MEMORY.md`

### 测试与发布

- 新增幂等键跨目标/跨动作回归测试：`1 passed`。
- 技师后端专项：`21 passed`；管理端测试：`107 passed`；管理端生产构建成功。
- 未发布生产，服务器 current 未改变；源码提交已推送到 `codex/technician/idempotency-scope-api`，待 CI 和 PR 审核。

### 待门店现场验收

- 使用授权测试账号完成顾客提交后看板同步、确认服务、服务结束、快记保存/失败重试及审计闭环。
- 自动化测试不替代真实手机、断网和并发场景验收。

## 2026-09-02 技师工作台可靠性加固（本地完成，待 PR）

### 修改内容

- 仅允许 `available`、`busy` 技师进入移动工作台，并在 `/technician/me` 中分别返回 Staff 与 Technician 状态。
- 确认服务、服务结束和画像保存的幂等键绑定技师、服务位、动作及请求体；复用到其他目标时返回 `409 IDEMPOTENCY_KEY_REUSED`，并对并发唯一性异常做安全兜底。
- 房间出现多个活动占用时聚合为“待核对”，不暴露顾客选单且禁止确认服务；响应补充 DIY 服务状态、只读资源状态和 `resource_control: external_read_only`。
- 技师离职/请假审批前校验未结束 DIY 服务，移动端增加冲突状态颜色、提示文案与说明抽屉。

### 涉及文件

- `hxy-server/app/api/technician.py`
- `hxy-server/app/api/technician_admin.py`
- `hxy-server/tests/test_technician_portal_api.py`
- `hxy-server/tests/test_technician_account_lifecycle.py`
- `admin-react/src/technician/TechnicianTodayPage.tsx`
- `admin-react/src/technician/technicianMobile.ts`
- `admin-react/src/technician/technician-mobile.css`
- `admin-react/tests/technician-workspace.test.ts`
- `docs/TEAM-MEMORY.md`

### 测试与发布

- 技师后端专项：`25 passed`；管理端测试：`108 passed`。
- `npx tsc -b` 与 `npm run build` 均通过；`git diff --check` 通过（仅换行符提示）。
- 尚未发布生产；当前分支为 `codex/technician/reliability-hardening`，待创建 PR 并通过六项 GitHub 检查后合并。

### 待门店现场验收

- 使用授权测试账号在手机上验证“顾客提交 → 看板同步 → 确认服务 → 服务结束 → 快记保存/重试 → 审计”完整链路。
- 验证断网重试、并发幂等、离职/请假拦截，以及智慧宝继续负责开房、离位、清洁和物理资源释放。

## 2026-09-02 技师账户与服务状态展示收口（本地完成，已推送，待 PR）

### 修改内容

- 技师“我的”页明确区分 Staff 登录账号状态与 Technician 服务状态，不再将账号 `active` 误显示为“在岗”。
- 账号状态显示为已启用、已停用、已离职或待激活；服务状态显示为空闲、服务中、休息、暂停服务或已离职。
- 补充专项回归测试，确保两套状态映射独立，保持 Staff 与 Technician 的对象边界。

### 涉及文件

- `admin-react/src/technician/TechnicianMePage.tsx`
- `admin-react/src/technician/technicianMobile.ts`
- `admin-react/tests/technician-mobile.test.ts`

### 测试与发布

- 管理端测试：`109 passed / 0 failed`。
- 技师后端专项：`33 passed / 0 failed`。
- 顾客端回归：`153 passed / 0 failed / 1 skipped`；顾客端生产构建通过。
- 管理端 `npx tsc -b`、`npm run build` 均通过；本分支相对 `origin/main` 的 `git diff --check` 通过。
- 技师代码提交已推送至 `codex/technician/profile-account-status`；尚未创建 PR。
- 尚未发布生产；本轮未访问或修改服务器、数据库或生产 release。

### 待门店现场验收

- 用已启用且服务状态分别为“空闲”“服务中”“休息”的授权测试账号确认状态显示与实际账号生命周期一致。
- 待 GitHub 六项检查和自动 Squash 合并完成后，才可进入数据库备份、Manifest 校验、生产健康检查和门店手机验收。
