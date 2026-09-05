# 顾客端“我的”升级 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将顾客端“我的”升级为可处理待评价、查看到店详情、识别会员有效期与累计节省，并落实手机号单设备登录的任务中心。

**Architecture:** 后端以 `users.customer_login_version` 作为单设备会话代次，新登录递增并写入 JWT，所有顾客鉴权统一校验。`GET /selection-sessions/mine` 返回顾客自己的到店记录聚合状态、评价状态、服务位和价格快照，详情与评价支持登录令牌访问；前端将两套记录合并为一个任务化列表，并以可访问的详情弹层承载完整信息。

**Tech Stack:** FastAPI、SQLAlchemy、Alembic、React 18、TypeScript、Node test runner、CSS。

## Global Constraints

- 顾客端不在线支付，只展示和提交项目及金额。
- 累计会员节省只统计已完成服务的历史价格快照：`max(门店价 - 会员价, 0)`。
- 取消、草稿、过期选单不计入累计节省；优惠券优惠不得计入会员节省。
- `localStorage` 仅保存登录令牌，不作为服务状态、价格或记录的事实源。
- 保持现有纯白、深绿、浅绿和少量暖金设计语言，不修改管理端或技师端页面。
- API、会员、价格和状态契约与实现、测试、文档必须同一变更交付。

---

### Task 1: 单设备登录契约

**Files:**
- Modify: `hxy-server/app/models/core.py`
- Modify: `hxy-server/app/core/security.py`
- Modify: `hxy-server/app/api/auth.py`
- Modify: `hxy-server/app/api/orders.py`
- Modify: `hxy-server/app/api/coupons.py`
- Modify: `hxy-server/app/api/selections.py`
- Create: `hxy-server/alembic/versions/20260905_customer_single_session.py`
- Test: `hxy-server/tests/test_h5_auth_api.py`

**Interfaces:**
- Produces: JWT claim `login_version: int`；失效响应 `401 {code: SESSION_REPLACED, message: ...}`。

- [x] 先补第二次登录后旧令牌访问 `/auth/h5/me`、订单、券和选单均返回 `SESSION_REPLACED` 的失败测试。
- [x] 运行专项测试确认因旧令牌仍有效而失败。
- [x] 增加登录代次字段、迁移和统一顾客鉴权函数；新登录递增代次并签发新令牌。
- [x] 运行专项测试确认新令牌有效、旧令牌失效。

### Task 2: 会员状态与真实累计节省

**Files:**
- Modify: `hxy-server/app/schemas/auth.py`
- Modify: `hxy-server/app/api/selections.py`
- Modify: `diy-web/src/customerAuth.ts`
- Modify: `diy-web/src/api.ts`
- Modify: `diy-web/src/profile.ts`
- Test: `hxy-server/tests/test_selection_api.py`
- Test: `diy-web/tests/profile.test.ts`

**Interfaces:**
- Produces: `member_expire_at`；我的记录 `service_completed_at`、`can_evaluate`、`evaluated`、`occupancy_status`、`store_total_cents`、`member_total_cents`；纯函数 `membershipSummary(records)`。

- [x] 补到期字段与仅统计已完成记录的累计节省失败测试。
- [x] 验证草稿、取消、未结束和优惠券不进入会员节省。
- [x] 最小实现返回字段和累计逻辑。
- [x] 运行前后端专项测试至通过。

### Task 3: 待评价与顾客本人详情

**Files:**
- Modify: `hxy-server/app/api/selections.py`
- Modify: `hxy-server/app/schemas/selection.py`
- Modify: `diy-web/src/api.ts`
- Test: `hxy-server/tests/test_selection_api.py`

**Interfaces:**
- Produces: `GET /selection-sessions/{id}/customer-detail`；`POST /selection-sessions/{id}/feedback` 接受本人 Bearer token 或原选单令牌。

- [x] 补本人可查看、他人不可查看、已完成未评价可评价、重复评价幂等的失败测试。
- [x] 运行测试确认现有接口不满足登录用户场景。
- [x] 实现所有权校验、详情聚合和双凭证评价。
- [x] 运行专项测试至通过。

### Task 4: “我的”任务中心界面

**Files:**
- Modify: `diy-web/src/components/ProfilePage.tsx`
- Modify: `diy-web/src/styles.css`
- Modify: `diy-web/src/profile.ts`
- Modify: `diy-web/src/customerAuth.ts`
- Test: `diy-web/tests/profile.test.ts`
- Test: `diy-web/tests/customer-auth.test.ts`

**Interfaces:**
- Consumes: 前三项新增字段和接口。
- Produces: 会员状态卡、累计会员省、待评价入口、统一到店记录筛选、可点击详情弹层、异地登录提示。

- [x] 补会员状态文案、到期状态、待评价筛选和异地登录动作的失败测试。
- [x] 运行测试确认失败原因均为行为尚缺失。
- [x] 实现任务中心信息架构、整卡点击、详情弹层和评价入口。
- [x] 完成 44px 触控、语义按钮、焦点与状态非纯颜色表达。
- [x] 运行顾客端专项测试至通过。

### Task 5: 契约、共享记忆与完整验证

**Files:**
- Create: `docs/contracts/customer-account-profile.md`
- Modify: `docs/TEAM-MEMORY.md`
- Modify: `docs/workstreams/customer.md`

**Interfaces:**
- Produces: 三端可复用的顾客登录、会员有效期、记录详情和评价契约。

- [x] 写明单设备会话、错误码、会员节省口径和本人记录权限。
- [x] 运行后端专项及完整相关测试。
- [x] 运行 `npm test`、`npm run build` 和 `git diff --check`。
- [x] 检查差异只包含顾客端、后端契约和必要迁移，不发布生产。

### Task 6: 会员本人动态核验（独立发布切片）

**Files:**
- Modify: `diy-web/src/components/ProfilePage.tsx`
- Modify: `admin-react/src/technician/*`
- Modify: `hxy-server/app/api/technician.py`
- Create: `hxy-server/app/models/membership_verification.py`
- Create: `docs/contracts/customer-membership-verification.md`
- Test: `diy-web/tests/profile.test.ts`
- Test: `admin-react/tests/*membership*.test.ts`
- Test: `hxy-server/tests/test_membership_verification.py`

**Interfaces:**
- Produces: 唯一可信设备、30秒一次性动态码、技师端 `membership_verify` 扫码与本店选单原子绑定；管理后台仅承担策略、换绑审批、异常和审计。

- [ ] 先补非可信设备禁用、动态码过期/重放、跨店/越权拒绝、店长独立权限和事务回滚的失败合同测试。
- [ ] 实现顾客端动态码与可信设备状态，不采集硬件指纹或在码中暴露个人资料。
- [ ] 实现技师端摄像头扫码和最小核验结果；扫码不附带确认/结束服务权限。
- [ ] 实现后端码状态机、幂等消费、选单绑定、会员价重算和审计事务。
- [ ] 完成三端测试、构建、差异检查及真机摄像头/弱网验证后，作为独立高风险切片发布。
