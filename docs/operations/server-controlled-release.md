# 服务器受控发布与 GitHub 异步备份

用户在 2026-11-14 明确采用本方案，并授权总控接手 DSH 未完成的修复。GitHub PR/CI 保留为二级检查与备份链路，不再阻塞服务器发布。启用事实以 CURRENT-STATE 和生产回执为准，脚本存在不等于已启用。

## 基线与权限

- 仅总控在审查和验证通过后，以 CAS / fast-forward 移动 `refs/heads/server-accepted`；新任务从此引用创建隔离 worktree。初始化必须绑定核实过的完整 SHA，拒绝覆盖已有引用。
- 发布仅接受 clean 且完整 SHA 匹配的开发 worktree。`prepare` 用 `git archive` 复制该提交，在隔离目录串行构建，不使用脏文件、忽略文件或生产 current 作为开发源。
- 迁移、真实数据导入、权限与凭据的授权仍分别处理。本入口不扩大迁移白名单，不导入会员或消费数据，不清理历史数据/备份。

## 1. 准备构建

```bash
python3 deploy/diy/server_release.py prepare --source <development-worktree> --sha <full-sha> --release-id server-<sha12>-<serial>
```

构建前检查至少 3 GiB 磁盘和 1536 MiB 可用内存，串行低优先级执行锁定依赖安装与构建。现有学习开关从已发布 marker 继承；缺失时拒绝猜测。构建后复核源树未变，导出 `workspaces/<release-id>`、`MANIFEST.sha256` 和 `build-report.json`。同 ID 已存在即停止，不覆盖。

`inspect` 或无参数调用只读显示当前 release、准备状态和待备份记录，不创建目录。

## 2. 精确验收记录

总控检查代码和相关合同测试；把实际验证证据放到 workspace 的 `evidence/`，每项为 JSON，至少包含：

```json
{"check":"release-contracts","source_sha":"<full-sha>","status":"passed","failed":0,"command":"python3 -m unittest discover -s tests -p test_*.py","environment":"isolated server worktree","timestamp":"<UTC time with timezone>"}
```

`check` 是实际执行的检查名，不可伪造结果。`source-review`、相关业务/合同测试和 `frontend-build` 应在本次验收清单中；已有同源有效证据可按明确范围引用，不能把旧 SHA 的结果伪装为新 SHA 测试。总控 acceptance 结构：

```json
{
  "schema":"server-release-acceptance@1",
  "release_id":"server-<sha12>-<serial>",
  "source_sha":"<full-sha>",
  "previous_release":"<observed-current-basename>",
  "manifest_sha256":"<manifest-file-sha256>",
  "build_report_sha256":"<build-report-file-sha256>",
  "accepted_at":"<UTC time with timezone>",
  "required_checks":["source-review","release-contracts","frontend-build"],
  "evidence":[{"kind":"source-review","path":"review.json","sha256":"<file-sha256>"}]
}
```

示例 evidence 需补齐全部 required_checks。缺项、失败、矛盾状态、外来 SHA、错误哈希、无时区、未来/过旧验收或变更的 previous release 均拒绝；验收记录最长有效 24 小时。

## 3. 单次发布与中断处理

```bash
python3 deploy/diy/server_release.py publish --release-id server-<sha12>-<serial> --acceptance <acceptance.json> --repo <development-worktree>
```

总控先核对/保存只读旧业务表保护基准。源 SHA 必须等于受审 server-accepted。入口先落盘 `release-records/attempt-<id>.json`，然后仅调用一次既有 deploy-production.sh；同一部署锁内再次核对 previous current，早于备份、恢复、迁移或切换。既有真实备份、隔离恢复、迁移拦截、Manifest、健康检查和失败回滚继续有效。

成功后回执包含安装后的 manifest 和备份哈希。超时、中断或失败留下 failed/uncertain/dispatched 状态；不得换 ID 盲重试，须先核查副作用。相同成功请求只在回执、验收 SHA、安装内容和 current 一致时返回 already_deployed，不再次调用部署。目录存在或出现 MANIFEST 本身都不代表成功。

总控再核对运行中源码、顾客/后台公网页面与 JS 哈希、no-store 入口缓存、匿名保护，以及旧表逐表数据/结构指纹。真实手机和门店操作仍需人工验收，不能以 HTTP 200 代替。

## 4. GitHub 异步备份

成功回执先独立持久化，再生成绑定精确 SHA 的本地 Git bundle 和 pending-github-backup 记录。备份失败记录为 failed/pending，不回滚已经成功的生产，不触发重复发布。

本机总控随后启动已有 GCM/官方 GitHub API 后台传输工具，把完整 Git 对象写到指定备份分支；校验 commit/tree 与实际远端 ref 后保存回执。只允许非强制更新，不改分支保护，不把凭据复制到服务器。传输失败保留 pending/failed，核对远端事实后再单独补备份；生产不等 GitHub。

当前本机协调器位于 `C:/Users/gaoji/Documents/ChatGPT/dsh-control-bridge/`，复用 `github_transport.py`；它限制仓库、基线和任务分支，不是公共服务。每次发布由总控显式启动一次后台备份任务，不宣称已存在无人值守调度器。服务器上的本地 bundle 尚不等于异机备份；必须取得 GitHub 或本机已校验副本后才能声称异机备份完成。

生产事实记录由发布总控更新到 CURRENT-STATE / WORK-STATUS，再推进 server-accepted 并异步备份。纯文档提交不重复部署。
