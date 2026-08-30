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

## 2026-08-30 顾客画像记录契约收口（本地完成，未发布）

### 修改内容

- 管理端画像快记与技师端统一年龄段编码（`18-25`）和安全服务特征标签，移除“局部硬结”“首次到店”“重点维护”等旧文案。
- 管理端备注改为“顾客自述、服务观察和服务注意事项”提示，前后端长度上限统一为 500 字。
- 保留技师画像写入的本人完成服务关联、门店隔离、字段白名单、医疗诊断词拦截、幂等和审计约束。

### 涉及文件

- `admin-react/src/pages/SelectionSessionsPage.tsx`
- `admin-react/tests/technician-workspace.test.ts`
- `hxy-server/app/schemas/profile.py`
- `hxy-server/tests/test_profile_record_contract.py`
- `docs/TEAM-MEMORY.md`

### 测试结果

- 管理端：`npm test` 110 passed；`npx tsc -b` 通过；`npm run build` 成功（Vite 4001 modules，保留既有 chunk 体积警告）。
- 后端画像/技师专项：22 passed；扩展员工生命周期专项 19 passed、1 failed，失败为基线中 legacy `staff` 未绑定 Technician 仍期望登录的契约冲突，与本次改动无关。
- Python 测试使用工作树显式 `PYTHONPATH` 和现有项目虚拟环境执行；存在既有 Starlette/httpx 弃用警告。

### 发布状态

- 未发布生产；未执行数据库迁移、备份、Manifest 切换或 API 重建。
- 当前分支：`codex/technician/profile-record-admin-closure`，待 CI/PR 审核。

### 待现场验收

- 使用门店授权手机验证真实账号权限、门店隔离、弱网/断网失败重试和并发重复点击。
- 完成“顾客提交 → 技师查看区位和选单 → 确认服务 → 服务结束 → 快记保存 → 审计核对”营业闭环；自动化测试不等同现场验收。
