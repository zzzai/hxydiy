# 荷小悦 DIY 项目协作仓库

本仓库 `zzzai/hxydiy` 同时是 Obsidian Vault 和项目代码/协作文档仓库，用于同步顾客端、管理后台、技师端三个工作窗口的共同事实。GitHub 当前仓库为公开仓库，敏感配置和真实顾客数据不得提交。

## 目录边界

- `diy-web/`：顾客端 H5，负责扫码、服务位绑定、菜单、价格、选单、提交和评价。
- `admin-react/`：管理后台，负责门店运营和权限范围内的管理能力。
- `hxy-server/`：FastAPI/SQLAlchemy 后端与 API，负责业务校验、状态、审计和数据隔离。
- `docs/`：共享记忆、工作流、发布记录和产品/架构文档；Obsidian 直接打开仓库根目录即可阅读。

## 使用方式

- Obsidian 打开本目录，日常阅读和编辑 Markdown。
- GitHub 仓库 `zzzai/hxydiy` 保存代码版本和跨窗口同步记录。
- `docs/TEAM-MEMORY.md` 只记录三端共同确认的事实和决策。
- `docs/workstreams/*.md` 记录各端当前任务、验证和交接事项。
- `docs/WORK-STATUS.md` 记录发布、回滚和现场验收历史。

## 三窗口同步

开始新任务前先执行：

```powershell
git fetch origin
git switch -c codex/<端>/<任务名> origin/main
```

已存在任务分支时，先 `git fetch origin`，再根据分支基线执行 rebase；不要把仅有文档的 `main` 误当成完整应用源码基线。

完成一个可验证的小任务后，在自己的任务分支提交并推送：

```powershell
git add docs
git commit -m "docs: update customer workstream"
git push -u origin codex/<端>/<任务名>
```

通过 GitHub Pull Request 合并到 `main`，不要从任何工作窗口直接推送 `main`。合并前先同步：

```powershell
git fetch origin
git rebase origin/main
```

涉及代码时，只提交负责目录和必要的测试；完成后运行对应端测试与生产构建。不要提交密码、验证码、私钥、AccessKey、真实顾客敏感信息、构建产物或测试截图。
