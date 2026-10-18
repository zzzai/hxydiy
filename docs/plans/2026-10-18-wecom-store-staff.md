# WeCom Store Staff Implementation Plan

**Goal:** 为已批准的一个本店店长和两个技师提供真实角色企微接入，不改变旧账号和业务数据。

**Architecture:** 复用当前员工、工作区授权、OAuth 和服务端角色门禁；店长身份不关联技师，使用唯一门店 `staff_scope` 会话，技师保持原合同。

**Tech Stack:** FastAPI、SQLAlchemy、Alembic、PostgreSQL、React、TypeScript。

## 边界与交付顺序

- [x] 身份与会话：先写 `test_wecom_store_manager.py` 验证真实角色/单店正向、缺失或多授权、总部、跨店、撤销、伪造 role/scope、技师不回归，再改 `app/services/wecom_staff.py`。
- [x] 迁移：仅将 `staff_external_identities.technician_id` 改为可空，FK、唯一约束和旧行不变；降级发现空值时拒绝，不删除身份。增加迁移测试，更新已有迁移终点测试与精确发布 allowlist。
- [x] 运维：独立正式员工批次工具；私有输入、默认预览、完整摘要确认、官方精确身份复核、同名/手机号/主体冲突拒绝、整批事务、随机密码只留哈希、审计和重放零新增。既有绑定 CLI 允许明确 `technician_id:null` 的合法店长，不借测试账户路径建正式账号。
- [x] 前端：技师窗口仅修改已声明的会话/Gate/pagehide 与差额测试；店长复用现有角色映射进入固定 `/admin/#/today`，不提供任意重定向或多工作区兜底。
- [x] 集成：定向 SQLite 与 PostgreSQL 角色/迁移/事务验证、前端单测/类型/必要合成移交检查；原67项隔离证据不重跑。OpenAPI/类型生成保持同步，必需 CI 不能跳过。
- [x] 生产：#280、精确 SHA `bfa16198b34666e28ff8ed2d5d7924000b909664`；3GiB容量门槛和串行限制保留。原GitHub容量失败后，同包经原发布器一次服务器恢复，真实备份恢复、迁移和版本核验通过；私有三人清单预览/应用/重放及59表旧资料保护完成。本人真实登录交现场验收，未标为已通过。

## 验收标准

店长每次请求必须重新匹配 active Staff、绑定、唯一 active 本店 `store_manager` 授权及 JWT 的 assignment/role/scope；撤销或换店立即拒绝。不得发总部权限或伪造技师编号。正常技师、密码登录、顾客数据可见范围、价格、服务单和余额不变。生成的密码、Secret、真实手机号、UserID 不进 Git 或公开报告。

生产发布事实与现场验收分别记录；执行采用已确认的逐项计划，无重复设计或执行方式审批。
