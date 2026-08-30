# 荷小悦 DIY 协作知识库

本目录同时是 Obsidian Vault 和 GitHub 协作文档仓库，用于同步顾客端、管理后台、技师端三个工作窗口的共同事实。它是共享记忆层，不等同于实际源码仓库。

## 使用方式

- Obsidian 打开本目录，日常阅读和编辑 Markdown；Obsidian 图谱、反向链接和搜索只是阅读工具，不能替代 Git 版本记录。
- GitHub 仓库 `zzzai/hxydiy` 保存共享记忆、工作流、决策和发布记录。
- 实际源码仍以各源码仓库的 Git 状态、API 合同和服务器生产 `current` 为准；开始编码前必须确认源码目录确实是 Git 仓库并已配置 `origin`。
- `docs/TEAM-MEMORY.md` 只记录三端共同确认的事实和决策。
- `docs/workstreams/*.md` 记录各端当前任务、验证和交接事项。
- `docs/WORK-STATUS.md` 记录发布、回滚和现场验收历史。
- `docs/AI-WINDOW-PROMPTS.md` 是三个窗口复制使用的公共启动提示词和端职责附录。

## 代码目录边界

以下目录在当前三窗口协作中承担不同职责，不能混用：

| 目录 | 定位 | 使用规则 |
|---|---|---|
| `C:\Users\gaoji\WorkBuddy\hxy-diy-monorepo-bootstrap` | 三端统一源码候选基线，包含 `admin-react`、`diy-web`、`hxy-server` | 当前为干净的 `codex/admin/monorepo-bootstrap` 分支；必须经 PR 审核并合并到 `main` 后，才作为所有新源码任务的唯一基线。 |
| `C:\Users\gaoji\WorkBuddy\2026-07-31-12-31-02` | 历史生产工作区和迁移核对来源 | 顶层不是 Git 仓库，且存在其他窗口未提交改动；只能用于核对遗漏和生产差异，不作为新任务的共同开发基线。 |
| `C:\Users\gaoji\Documents\ChatGPT\hxy-diy` | Obsidian Vault 和共享协作文档工作区 | 用于 Markdown 记忆、决策、交接和发布记录，不存放或替代完整三端源码。 |

当前 `origin/main` 仍只有文档，尚未包含三端源码。源码基线 PR 合并前，不得从 `origin/main` 创建三端代码任务分支，也不得将代码复制进本 Obsidian 文档工作区。生产版本始终以服务器部署目录的实际 `current`、生产 API 和数据库为准，而非任何本地目录名称或分支名称。

## 三窗口同步

每个窗口使用 `docs/AI-WINDOW-PROMPTS.md` 中的公共提示词，再追加自己负责端的提示词。窗口之间不共享聊天上下文，必须通过 Git 文档和代码仓库交接。

开始工作前，在对应的源码仓库和本仓库分别执行：

```powershell
git fetch origin
git status --short --branch
git log -5 --oneline --decorate
```

新任务从远端主分支创建实际任务分支，不直接修改或推送 `main`：

```powershell
git switch -c codex/<端>/<实际任务名> origin/main
```

已有任务分支则先同步后再工作：

```powershell
git switch codex/<端>/<实际任务名>
git rebase origin/main
```

完成一个可验证的小任务后，只提交自己负责的文件，推送分支并创建 Pull Request。涉及 API、状态机、权限、服务位、价格或画像字段时，先更新 `docs/TEAM-MEMORY.md`，再修改实现；完成后更新对应 `docs/workstreams/*.md` 和 `docs/WORK-STATUS.md`。

不要提交密码、验证码、私钥、AccessKey、真实顾客敏感信息、构建产物或测试截图。

## 是否需要额外知识库

目前不需要安装向量数据库或另外的知识库产品。三个窗口的最小可用组合是：Obsidian 负责查看 Markdown，GitHub 负责版本、分支、PR 和审计，源码仓库负责代码。

只有在文档规模明显超过人工检索能力，或需要跨大量历史资料做语义检索时，才评估额外 RAG/知识库；在此之前先保持 `TEAM-MEMORY` 短小、工作流按端隔离、任务上下文按需读取，避免把整个项目文档或代码库一次性塞进提示词。
