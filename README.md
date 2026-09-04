# 荷小悦 DIY Monorepo

本仓库同时保存顾客端、管理端、技师端、共享后端、合同测试和项目记忆。`origin/main` 是三个开发窗口唯一的共享事实源。

## 使用方式

- 顾客端代码：`diy-web/`。
- 管理端和技师移动端前端：`admin-react/`。
- 三端共享后端：`hxy-server/`。
- Obsidian 可以打开本目录阅读和编辑 Markdown，但不承担同步职责。
- GitHub 私有仓库 `zzzai/hxydiy` 同步代码、迁移、契约、测试和项目记忆。
- `docs/CONTEXT-MANIFEST.md` 规定默认上下文、权威顺序和更新责任。
- `docs/CURRENT-STATE.md` 是三个窗口的当前状态入口。
- `docs/TEAM-MEMORY.md` 只记录三端共同确认的事实和决策。
- `docs/workstreams/*.md` 记录各端当前任务、验证和交接事项。
- `docs/WORK-STATUS.md` 记录发布、回滚和现场验收历史。

## 三窗口同步

三个窗口分别使用独立 worktree 和 `codex/<端>/<任务>` 分支。开始工作前先保存本地改动，再执行：

```powershell
git fetch origin
git rebase origin/main
```

随后只读取 `AGENTS.md`、`docs/CONTEXT-MANIFEST.md`、`docs/CURRENT-STATE.md` 和本端 workstream。涉及跨端契约时再读取团队记忆和对应 contract。

完成一个可验证的小任务后，在自己的任务分支提交并推送。跨端契约与实现、测试和共享记忆必须进入同一个 PR：

```powershell
git add docs
git commit -m "docs: update customer workstream"
git push -u origin codex/<端>/<任务名>
```

通过 GitHub Pull Request 合并到 `main`，不要从任何工作窗口直接推送 `main`。生产必须从已合并主干提交构建；发布者负责更新当前状态和发布历史。

不要提交密码、验证码、私钥、AccessKey、真实顾客敏感信息、构建产物、完整日志、临时截图或聊天记录。当前规模不引入 RAG、向量数据库或第二套知识库。
