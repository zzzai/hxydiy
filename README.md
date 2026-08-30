# 荷小悦 DIY 协作知识库

本目录同时是 Obsidian Vault 和项目协作文档仓库，用于同步顾客端、管理后台、技师端三个工作窗口的共同事实。

## 使用方式

- Obsidian 打开本目录，日常阅读和编辑 Markdown。
- GitHub 私有仓库 `zzzai/hxydiy` 保存版本和跨窗口同步记录。
- `docs/TEAM-MEMORY.md` 只记录三端共同确认的事实和决策。
- `docs/workstreams/*.md` 记录各端当前任务、验证和交接事项。
- `docs/WORK-STATUS.md` 记录发布、回滚和现场验收历史。

## 三窗口同步

开始工作前先执行：

```powershell
git pull --rebase origin main
```

完成一个可验证的小任务后提交自己的文档：

```powershell
git add docs
git commit -m "docs: update customer workstream"
git push origin main
```

不要提交密码、验证码、私钥、AccessKey、真实顾客敏感信息、构建产物或测试截图。
