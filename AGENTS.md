# 项目协作说明

- 所有回复使用简体中文。
- 生产级业务修正、价格逻辑和用户体验改动，必须先完成本地与服务器验证，再按风险边界发布。

## 三窗口共享记忆

- 每个任务从最新 `origin/main` 创建或同步独立 worktree；未提交文件和聊天内容不算共享事实。
- 开始任务默认读取 `docs/CONTEXT-MANIFEST.md`、`docs/CURRENT-STATE.md` 和本端 `docs/workstreams/<端>.md`，其他资料按需检索。
- API、价格、状态机、权限、服务位或画像字段等跨端契约发生变化时，业务实现、合同测试、`docs/TEAM-MEMORY.md` 和相关 `docs/contracts/` 必须在同一个 PR 更新。
- 实际执行生产发布的窗口负责更新 `docs/CURRENT-STATE.md`，并在 `docs/WORK-STATUS.md` 顶部追加已核验事实。
- Obsidian 只作为本仓库 Markdown 的阅读和编辑工具；共享记忆以合并后的 Git 主干为准。

## `_build_plan/`

`_build_plan/` 文件夹包含初始 PRD 和各里程碑提示，用于本项目初始建设阶段。它们仅用于文档和执行指引，不是功能代码；项目中的代码、配置、运行时逻辑和测试不得导入、读取或依赖其中内容。

不要把 `_build_plan/` 视为长期产品文档。随着产品演进，其中的假设可能过时；初始里程碑完成并交付后，应删除整个目录。
