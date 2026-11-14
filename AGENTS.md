# 项目协作说明

- 所有回复使用简体中文。
- 代码、命令和 commit message 使用英文。
- 在用户已授权范围内完成实现、验证和交付；已确认的设计或计划直接执行，常规步骤不重复确认。只有缺失决策会实质改变结果、扩大范围或涉及未授权的不可逆操作时才询问。
- Skills 按需使用，用户明确要求优先于通用技能流程；不因技能重复设计审批、计划审批、执行方式选择或阶段停顿。确需暂停时说明阻碍及来源。
- 计划写清结果、边界和验收即可；简单修改不强制另写设计、逐步代码计划或单独文档提交。允许根据实现证据调整步骤。
- 测试按风险选择：行为修复验证真实行为和回归；文案、排版和指令变更不强制 TDD 或照抄实现的源码字符串测试。相关检查及必需 CI 通过后，无新改动、失败或未解风险不重复扩大测试。价格、权限、门店隔离、幂等和顾客数据可见范围保留合同验证。
- 只加载能解决当前问题的技能及资料，不按关键词或微小可能性遍历技能。默认单代理完成；仅在有委派授权且独立子任务有收益时委派。
- 生产级业务修正、价格逻辑和用户体验改动，必须先完成本地与服务器验证，再按风险边界发布。

## 三窗口共享记忆

- 开发任务从最新 `origin/main` 创建或同步独立 worktree，已有隔离工作区可继续使用；只读问答不要求新建或同步。保护未提交文件，不覆盖其他窗口工作；未提交文件和聊天内容不算共享事实。
- 新接手项目、跨端修改或核对发布状态时读取 `docs/CONTEXT-MANIFEST.md`、`docs/CURRENT-STATE.md` 和相关端 workstream；连续任务复用已读上下文，局部修改按需读取相关资料。
- API、价格、状态机、权限、服务位或画像字段等跨端契约发生变化时，业务实现、合同测试、`docs/TEAM-MEMORY.md` 和相关 `docs/contracts/` 必须在同一个 PR 更新。
- 实际执行生产发布的窗口负责更新 `docs/CURRENT-STATE.md`，并在 `docs/WORK-STATUS.md` 顶部追加已核验事实。
- Obsidian 只作为本仓库 Markdown 的阅读和编辑工具；共享记忆以合并后的 Git 主干为准。

## 三端统一脚本优先交付

- 模型节约协议见 `docs/script-first-delivery.md` 的“紧凑交接与模型介入”：单任务单写入窗口；派发只传目标、工作区、修改边界和验收条件；复用证据，失败才展开日志。过程回执合并，不逐条唤醒总控或转述给用户。
- 统一执行 `docs/script-first-delivery.md`：脚本等待、只读最终报告、失败才介入。
- 本地验证按改动范围选择；PR 和发布等待复用 `tools/release/`，读取精简报告，失败才定向查日志，避免重复查询和重复部署。
- 后台启动后可继续独立工作，需要交接时提供报告路径，不强制结束整个任务。`terminal=false` 是进行中，不是成功；完成声明区分本地、合并、生产和现场验收。
- `-Merge` 是单独的写操作开关，仅在用户已授权提交/合并本次变更时使用；脚本只合并指定 PR 的完整 SHA，不绕过检查，不强推、不自动重跑/回滚/修改业务。
- 云端 AI 审查默认关闭，只有维护者明确启用才调用；脚本及 CI 等待本身不消耗模型 token，编写代码、人工请求 AI 审查和失败分析仍消耗。

## 服务端受控发布与 GitHub 异步备份

- 生产发布走服务端受控入口 `deploy/diy/server_release.py`（`prepare` / `inspect` / `publish`），复用 `deploy/diy/deploy-production.sh` 及既有 create/activate/capacity/backup/restore/migration/manifest/lock/health/rollback 门禁，不重复、不削弱这些门禁。
- 发布必须来自 clean 且精确 SHA 的开发 worktree；禁止从脏工作区或 current 直接发布。`prepare` 只做串行锁定依赖构建并导出不可变 workspace，默认 `inspect` 只读；只有显式 `publish` 才消费精确 SHA 的协调者 acceptance 记录并单次派发部署。
- acceptance 记录必须绑定 source SHA、previous release、checks 与 artifact manifest，不能是任意 true 标志；缺失/失败/过期证据、意外 current、错误产物哈希都拒绝，拒绝时不调用任何部署命令。
- 前端按串行、低优先级、锁定依赖构建，并显式保留现有构建标志（`VITE_STAFF_LEARNING_ENABLED` / `staff-learning-build.json`、客户 base path）；不得静默关闭学习等当前前端构建特性。
- 已评审发布基线为 `server-accepted` 引用（仅协调者在复核后以 compare-and-swap / fast-forward 移动）；`origin/main` 是异步镜像而非静默过期的权威源。生产 current 与部署回执仍是生产真相。
- 接受/部署后生成绑定精确 SHA 的 pending GitHub backup 记录与本地已验证 Git bundle；服务器不安装凭证、不强推 GitHub、不更改分支保护、无回执不宣称镜像完成。GitHub PR/CI 保留为二级检查，不再是发布关键路径。

## `_build_plan/`

`_build_plan/` 文件夹包含初始 PRD 和各里程碑提示，用于本项目初始建设阶段。它们仅用于文档和执行指引，不是功能代码；项目中的代码、配置、运行时逻辑和测试不得导入、读取或依赖其中内容。

不要把 `_build_plan/` 视为长期产品文档，其中假设可能过时；当前依据使用 PRD 与 contracts。本条不构成自动删除目录的授权。
