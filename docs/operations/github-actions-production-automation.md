# GitHub Actions 自动审核与生产发布

本文定义仓库内置的 PR 审核、CI 验收和生产发布边界。它是发布操作手册，不代表当前环境已经配置或已经发布。

## 自动化链路

1. `AI PR Review` 由 `pull_request_target` 触发，只通过 GitHub API 读取 PR 标题、描述和 diff，不 checkout、不执行 PR 分支代码；敏感路径跳过、凭据模式脱敏。
2. AI 结果写入 PR 头 SHA 的 `AI PR Review` Check Run：缺密钥、请求失败、JSON 无效或发现 `critical/high` 均为失败；其他结果为成功并发表评论。AI 不自动批准。
3. `Trusted PR Gate` 由默认分支上的 `pull_request_target` 定义，拒绝 fork PR，仅在隔离 Runner、无 secrets、只读权限下检出 PR merge ref，运行静态契约、管理端、顾客端和后端验证，并把结果写回 PR 头 SHA。
4. `Auto Merge PR` 由 `workflow_run` 监听 AI 与可信门禁，仅接受同仓库、非草稿、目标为 `main` 且触发 run 与当前 head SHA 一致、全部必需检查成功的 PR，调用带精确 `sha` 的 squash merge。检查未完成、PR 更新、fork 或 GitHub 返回 405/409/422 时只跳过，不强行覆盖。
5. `CI` 仍在 PR 和 `main` push 上运行，作为开发反馈和发布前回归；生产自动合并不把 PR 自定义的 CI 定义当作唯一信任根。
6. `Deploy Production` 没有手工 SHA 发布入口，只接收 `main` 上名为 `CI` 且结论为成功的 workflow run，并绑定 GitHub `production` Environment。环境审批通过后，构建 release、固定 SSH 主机指纹、上传到服务器，再由远端脚本执行备份、恢复演练、Manifest 校验、原子切换和健康检查。

## GitHub 配置

在仓库 Settings → Actions → Secrets and variables → Actions 中添加以下仓库级 Secret：

- `OPENAI_API_KEY`：AI 审核密钥；只用于 `AI PR Review`。

在仓库 Settings → Environments → `production` 中配置至少一名 Required reviewer，并添加以下 Environment Secrets。该审批只保护生产发布，不参与 PR 合并；用户已授权取消 PR 人工审核，但未授权取消生产环境保护：

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

## 当前验收状态（2026-09-01）

- PR #7（`codex/admin/cicd-gate-hardening-main`）正在迁移门禁实现；本地契约测试与工作流 YAML 校验已通过，CI 的管理端、顾客端、后端和静态检查已通过。
- GitHub Actions 自 2025 年起不允许通过 REST 更新由 Actions 创建的 Check Run；Trusted Gate 和 AI Review 均采用“每次运行创建当前 head SHA 的新结果检查”，不再调用 `checks.update`。
- Trusted Gate 的执行 job 直接使用 `Trusted / ...` 名称，required checks 采用 GitHub Actions 原生 job checks，避免通过 REST API 创建或更新 Check Run 导致权限和状态漂移。
- PR #7 的 Trusted Gate 旧运行曾因默认分支仍加载旧工作流而失败；迁移提交合并后必须重新触发并确认新名称的检查真实出现。
- AI PR Review 当前仍需仓库有效的 `OPENAI_API_KEY`；无效或缺失密钥必须保持失败，不能改为可选或伪造成功。
- 已完成针对发布脚本和 Compose 的 Codex Security diff scan：覆盖 4 个发布文件，0 个可报告发现；该结果不替代真实 Runner、非生产服务器和生产 Environment 演练。
- `AI PR Review`、`Trusted PR Gate` 和 `Auto Merge PR` 必须先合并到 `main`，才会作为默认分支工作流对后续 PR 生效；迁移 PR 本身需记录 bootstrap 例外，不能据此宣称门禁已完成验收。
- 生产发布仍未执行。公网仓库无法匿名读取 Ruleset/Environment 配置，因此必须由仓库管理员在 GitHub 页面确认规则已启用。

## 必须启用的 GitHub Ruleset

在 `Settings → Rules → Rulesets` 为 `main` 设置：

- 必须通过 Pull Request，禁止直接 push；
- 必须通过 `Trusted / Static contracts`、`Trusted / Admin tests and build`、`Trusted / Customer tests and build`、`Trusted / Backend tests`、`Trusted PR Gate` 和 `AI PR Review`；这些是 Check Run 的实际名称，不要按 GitHub 页面显示的 workflow 分组名称填写；
- 将 required approving reviews 设为 `0`，不配置 CODEOWNERS 强制审批；
- 启用“分支必须最新后才能合并”和线性/合并队列（仓库规模扩大后优先启用 Merge queue）；
- 允许 GitHub Auto-merge。自动合并工作流仍会再次按当前 head SHA 校验，Ruleset 是最终硬门禁。

## 成熟方案对照与采用基线

- GitHub Rulesets + Required status checks：作为不可绕过的合并硬门禁；required approving reviews 设为 0，满足“无人工 PR 审核”。
- Trusted PR Gate：借鉴 GitHub `pull_request_target` 的默认分支信任模型，隔离 Runner 运行 PR merge ref，不给 secrets 和写权限。
- AI PR Review：只做结构化风险检测和可追溯评论，失败即 Check Run failure；不授予批准权限，不替代测试、SAST 和依赖审计。
- CodeQL、GitHub Secret Scanning/Push Protection、Dependabot 或 Renovate、OSSF Scorecard：建议在完整 monorepo 合并后作为独立 required checks 增加。
- GitHub Auto-merge 先采用仓库内受控 `workflow_run` 实现；门店数量和并发 PR 增长后迁移到 Merge queue，继续保留精确 SHA 校验。
- 生产发布沿用 GitHub Environment、OIDC/短期凭证（当前 SSH 专用密钥为过渡方案）、备份恢复演练、Manifest、健康检查和自动回滚。PR 无人工审核不等于生产环境取消保护。

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
