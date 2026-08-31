# GitHub Actions 自动审核与生产发布

本文定义仓库内置的 PR 审核、CI 验收和生产发布边界。它是发布操作手册，不代表当前环境已经配置或已经发布。

## 自动化链路

1. `AI PR Review` 由 `pull_request_target` 触发，只通过 GitHub API 读取 PR 标题、描述和 diff，不 checkout、不执行 PR 分支代码。
2. AI 返回结构化 findings；`critical/high` 以 `REQUEST_CHANGES` 阻断，其他结果只发表评论。AI 永不自动批准、永不自动合并。
3. `CI` 在 PR 和 `main` push 上运行仓库契约、敏感信息扫描、管理端/顾客端测试与生产构建、后端测试。缺少完整三端源码时只报告 baseline 未就绪，不把文档仓库误判成可发布产品。
4. `Deploy Production` 只接收 `main` 上成功的 CI 运行，并绑定 GitHub `production` Environment。环境审批通过后，构建 release、固定 SSH 主机指纹、上传到服务器，再由远端脚本执行备份、恢复演练、Manifest 校验、原子切换和健康检查。

## GitHub 配置

在仓库 Settings → Actions → Secrets and variables → Actions 中添加以下仓库级 Secret：

- `OPENAI_API_KEY`：AI 审核密钥；只用于 `AI PR Review`。

在仓库 Settings → Environments → `production` 中配置至少一名 Required reviewer，并添加以下 Environment Secrets：

- `PRODUCTION_SSH_HOST`：生产服务器地址。
- `PRODUCTION_SSH_USER`：生产 SSH 用户。
- `PRODUCTION_SSH_PRIVATE_KEY`：仅用于发布的专用 ed25519 私钥。
- `PRODUCTION_SSH_KNOWN_HOSTS`：固定的 `known_hosts` 行，禁止在工作流中调用 `ssh-keyscan`。

可选 Variables：

- 仓库级 `OPENAI_REVIEW_MODEL`：审核模型，默认 `gpt-5.2`。
- `production` Environment 级 `PRODUCTION_ROOT`：默认 `/root/hxy-diy-20260811`。

服务器上仍由运维保管 `/root/hxy-diy-20260811/deploy/diy/.env`。七牛云密钥、数据库密码、JWT 密钥、短信和支付密钥不得进入仓库或 GitHub Actions 日志。

## 发布前提

- 完整 monorepo 基线必须已经合并到 `main`，包含 `admin-react`、`diy-web`、`hxy-server` 和 `deploy/diy`。
- 管理端、顾客端测试和 TypeScript/生产构建通过；后端专项测试通过。
- 发布脚本会比较新旧 Alembic 文件列表。检测到迁移变化时自动阻断，不会自动 downgrade；迁移必须走单独审批、备份和恢复方案。

## 远端脚本保证

- 先使用 `pg_dump -Fc` 备份 PostgreSQL，再写入 SHA-256 校验文件。
- 在正式切换前创建临时数据库并执行 `pg_restore`，验证备份可恢复。
- release 使用临时目录构建，生成逐文件 `MANIFEST.sha256`，校验通过后原子替换 `current`。
- API、管理端和顾客端健康检查全部通过才算成功。
- 任一步骤失败时切回部署前 `current`，恢复 API 容器；数据库不自动降级，恢复数据库必须使用已校验备份并由人工执行。

## 手工演练

先在非生产服务器设置 `HXY_DIY_RELEASE_ROOT`，准备完整源码和 `.env`，执行：

```bash
deploy/diy/deploy-production.sh <release-id> /root/hxy-diy-20260811/workspaces/<release-id>
```

演练必须记录备份文件、校验和、健康检查结果以及回滚结果。GitHub 自动发布只负责已审查提交的传输和执行，不替代店长/管理员/员工账号的现场验收。
