# 顾客端工作流

## 负责范围

- 顾客扫码进入、门店与服务位绑定。
- 菜单、项目详情、门店价/团购价/会员价和节省金额。
- 匿名选单、会员登录、提交给前台、服务状态查看和评价。
- 顾客端移动体验、无障碍、刷新/返回/断网恢复和回归测试。

## 明确不做

- 技师派单、接单、开房、离位、清洁和物理资源释放。
- 管理后台权限模型和运营配置页面。
- 智慧宝资源状态的写入。

## 当前任务

- 状态：足部精修素材已推送，PR #5 待审核/合并
- 负责人：顾客端窗口
- 开始前读取：`PROJECT-CONTEXT-20260826.md`、`TEAM-MEMORY.md`、`WORK-STATUS.md`

## 跨端变更规则

涉及 API 字段、价格、服务状态、服务位绑定或提交契约时，先在 `TEAM-MEMORY.md` 登记影响，再修改代码；完成后在本文件记录测试结果和交接事项。

## 验证要求

- 顾客端测试必须通过。
- 顾客端生产构建必须通过。
- 会员、非会员、匿名三种身份均需验证。
- 线上发布必须记录 release、Manifest、健康检查和待现场验收项。

## 2026-08-31 足部精修素材同步提交

- 顾客端分支：`codex/customer/source-baseline`。
- 本地提交：`2222d99 feat(customer): update foot refinement assets`。
- 变更范围：足部精修主图、详情长图、详情文案及素材格式/构建一致性回归测试；未修改后端、技师端或管理端。
- 本地验证：`npm ci`、`npm test`（153 passed / 0 failed / 0 skipped）、`HXY_PRODUCTION_SMOKE=1 npm test`（153 passed / 0 failed / 0 skipped）、`npm run build`、`git diff --check` 均通过。
- 推送状态：`codex/customer/source-baseline` 已推送到 GitHub；已创建 [PR #5](https://github.com/zzzai/hxydiy/pull/5)，目标基线为 `codex/technician/profile-record-admin-closure`。
- 发布状态：未发布生产；当前线上仍以既有 `customer-foot-refine-illustration-20260830-1` 为准。
