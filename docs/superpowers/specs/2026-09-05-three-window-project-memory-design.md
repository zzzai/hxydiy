# 三窗口项目记忆与单仓协作设计

## 目标

让顾客端、管理端、技师端三个 Codex 窗口在同一个私有 GitHub Monorepo 中独立开发，同时持续获得一致、可追溯、低 Token 的项目记忆。聊天记录不作为长期事实源，Obsidian 只作为 Markdown 阅读和编辑工具。

## 现状问题

- 项目已经使用同一 Git 仓库和多个 worktree，但共享文档存在未提交、过期和重复记录。
- `CURRENT-STATE.md` 尚未进入主干；三个窗口无法稳定取得同一份当前生产事实。
- `TEAM-MEMORY.md` 仍包含已被 `service_reference_v1` 替代的画像决策。
- 旧 `three-window-protocol` 分支基于过期主干，未形成可执行闭环。
- 生产状态、工作流状态和历史记录互相重复，发布后容易只更新其中一处。

## 选定方案

采用“一个远端仓库、一个主干事实源、三个开发 worktree、四层记忆”的结构。

### 仓库与工作区

- `origin/main` 是代码、契约和项目记忆的唯一共享事实源。
- `hxy-diy` 主目录用于主干协调和共享状态核对，不承载三个端的功能开发。
- 顾客端、管理端、技师端分别使用独立 worktree 和 `codex/<端>/<任务>` 分支。
- 三端代码继续位于同一仓库：`diy-web/`、`admin-react/`、`hxy-server/`。
- 不再把无 Git 元数据的外部源码副本视为正式开发或交付来源。

### 四层记忆

1. `docs/CURRENT-STATE.md`：不超过约 150 行，只记录当前生产版本、三端当前状态、跨端阻塞和下一步。
2. `docs/TEAM-MEMORY.md`：只记录长期稳定的业务边界、权限原则、数据定义和已确认决策。
3. `docs/contracts/`：保存 API、字段、状态机、错误码和标签体系等可测试契约。
4. `docs/WORK-STATUS.md`：追加发布、回滚和验收历史；仅按关键词检索，不作为每轮默认上下文。

`docs/workstreams/customer.md`、`admin.md`、`technician.md` 分别记录本端的当前任务、验证结果和交接事项。

### 上下文读取规则

每个窗口开始任务时只默认读取：

1. `AGENTS.md`
2. `docs/CONTEXT-MANIFEST.md`
3. `docs/CURRENT-STATE.md`
4. 自己的 `docs/workstreams/<端>.md`

涉及 API、价格、状态机、权限、服务位或画像字段时，再读取 `TEAM-MEMORY.md` 和对应 `docs/contracts/`。历史 PRD、完整 `WORK-STATUS.md`、旧聊天、构建日志和截图只在明确需要时检索。

### 更新责任

- 本端窗口维护自己的 workstream 文件。
- 改变跨端契约的窗口，必须在同一个 PR 中更新实现、合同测试、`TEAM-MEMORY.md` 和相关 contract。
- 实际执行生产发布的窗口负责更新 `CURRENT-STATE.md` 和 `WORK-STATUS.md`。
- 共享事实只有合并到 `origin/main` 后才算同步；未提交文件和聊天结论不算共享记忆。

### 权威优先级

发生冲突时按以下顺序判断：

1. 生产服务器、数据库和公网接口的实时核验
2. `origin/main` 的代码、迁移和测试
3. `docs/contracts/`
4. `docs/CURRENT-STATE.md`
5. `docs/TEAM-MEMORY.md`
6. 各端 workstream
7. `docs/WORK-STATUS.md`
8. 历史聊天和旧提示词

## 本轮实施范围

- 新增 `docs/CONTEXT-MANIFEST.md`，固化读取边界、权威顺序和责任人规则。
- 将 `docs/CURRENT-STATE.md` 正式纳入 Git，并更新到生产 release `main-bf0bddf-20260905-1`、数据库迁移 `20260904_service_reference_v2`。
- 清理 `TEAM-MEMORY.md` 中已经失效的旧画像决策，写入 `service_reference_v1` 跨端契约。
- 更新三个 workstream，准确反映顾客端、管理端、技师端对新版服务参考的当前职责和待办。
- 收紧 `AGENTS.md`：所有窗口必须以主干共享记忆为准，跨端契约随代码同 PR 更新。
- 新增轻量只读检查脚本，检查核心记忆文件是否存在、是否被 Git 跟踪、是否仍包含明确的过期标记；不引入数据库、RAG 或外部服务。
- 更新三窗口启动提示词，改为短提示词引用共享文件，不再复制大量背景资料。

## 不在本轮范围

- 不引入向量数据库、RAG、Obsidian Sync 或新的 SaaS 知识库。
- 不改变三端业务代码、数据库结构、生产服务或 GitHub 分支保护规则。
- 不删除历史 worktree、旧分支或用户未提交文件。
- 不自动提交或发布生产。

## 工作流

### 开始任务

窗口执行 `git fetch origin`，确认基线包含最新 `origin/main`，再读取最小上下文文件。功能分支落后主干时先同步；不得仅凭本地旧文档继续开发。

### 完成任务

窗口运行本端测试和受影响的合同测试，更新本端 workstream；跨端变化同步更新合同与团队记忆；随后提交 PR。生产发布完成后，由发布者追加当前状态和发布事实。

### 冲突处理

如果共享文档与代码或生产不一致，先实时核验，再在当前任务 PR 中修正文档。不得为了保留旧记录而让 `CURRENT-STATE.md` 同时出现多个“当前版本”。

## 验证标准

- 核心记忆文件全部被 Git 跟踪。
- 三个 workstream 均明确负责人、当前状态和跨端交接。
- `TEAM-MEMORY.md` 不再包含已废止的年龄、性别、体型、职业画像方案。
- `CURRENT-STATE.md` 与本次已核验生产 release、镜像和 Alembic head 一致。
- 三窗口启动提示词只要求读取最小上下文，并明确 Git 同步步骤。
- 轻量检查脚本在当前主干内容上通过。
- `git diff --check` 通过，不修改任何业务运行逻辑。

## 风险控制

- 当前主目录存在其他窗口的未提交文档，本轮只在独立 worktree 中修改。
- 旧协议分支保留不动，待新方案合并后再单独决定是否归档。
- 生产事实会标注核验时间；超过当前任务需要时必须重新连接服务器验证，不能把文档当实时监控。
