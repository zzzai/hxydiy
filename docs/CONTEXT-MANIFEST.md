# hxy-diy 上下文清单

本文件规定三个开发窗口如何读取和更新项目记忆。目标是让事实一致，同时避免每轮加载整个仓库、全部历史或旧聊天。

## 唯一共享事实源

- 代码、迁移、契约和共享记忆只有合并到 `origin/main` 后，才算三个窗口已经同步。
- 本地未提交文件、单个任务分支、Codex 对话、Obsidian 缓存和生产服务器上的临时文件都不是共享事实源。
- Obsidian 只用于阅读和编辑本仓库 Markdown，不使用第二套同步或记忆目录。

## 每次任务默认读取

1. 根目录 `AGENTS.md`
2. 本文件
3. `docs/CURRENT-STATE.md`
4. 当前端的 `docs/workstreams/customer.md`、`admin.md` 或 `technician.md`

## 按需读取

- API、价格、状态机、权限、服务位或画像字段变化：读取 `docs/TEAM-MEMORY.md`、相关 `docs/contracts/`、源码和合同测试。
- 追溯发布、回滚或历史决策：先用 `rg -n` 搜索 `docs/WORK-STATUS.md`，只读取命中片段。
- 产品设计：读取当前任务对应的 PRD、设计说明或实施计划。
- 生产判断：实时核对生产服务器、数据库、容器和公网接口，不能只依据文档。

## 默认排除

- 完整历史聊天、完整构建日志、旧截图和失败探索过程。
- 与当前任务无关的其他端源码和工作流全文。
- `_build_plan/` 中已经完成或过期的初始建设资料。
- 密码、验证码、AccessKey、私钥、生产环境变量和真实顾客隐私。

## 权威顺序

出现冲突时，依次采用：

1. 生产服务器、数据库和公网接口的实时核验
2. `origin/main` 的代码、迁移和测试
3. `docs/contracts/`
4. `docs/CURRENT-STATE.md`
5. `docs/TEAM-MEMORY.md`
6. 各端 workstream
7. `docs/WORK-STATUS.md`
8. 历史聊天和旧提示词

发现冲突的窗口必须在当前任务中修正文档，不能同时保留两个“当前版本”。

## 更新责任

- 顾客端、管理端、技师端窗口分别维护自己的 workstream。
- 改变跨端契约的窗口，在同一个 PR 中更新业务实现、合同测试、`TEAM-MEMORY.md` 和相关 contract。
- 实际执行生产发布的窗口更新 `CURRENT-STATE.md`，并在 `WORK-STATUS.md` 顶部追加发布事实。
- 其他窗口同步前先保存自己的未提交工作，再执行 `git fetch origin` 并将最新 `origin/main` 合入或 rebase 到当前任务分支。

## 上下文边界负责人

负责合并或发布当前变更的窗口负责本次上下文边界：只写会影响后续决策的事实，删除已被新决策明确替代的内容。项目规模尚不需要 RAG 或向量数据库；优先使用结构化 Markdown、Git 历史和 `rg` 定向检索。
