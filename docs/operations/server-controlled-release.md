# 服务端受控发布运行手册

生产发布已由服务端受控入口取代 GitHub PR/CI 作为关键路径。入口为
`deploy/diy/server_release.py`，复用 `deploy/diy/deploy-production.sh` 及既有
create/activate/capacity/backup/restore/migration/manifest/lock/health/rollback
门禁，不重复、不削弱这些门禁。GitHub PR/CI 保留为二级检查与异步镜像。

## 安全边界

- 只从 clean 且精确 SHA 的开发 worktree 构建；禁止从脏工作区或 current 直接发布。
- 服务器不安装任何 GitHub 凭证，不 push / force-push，不更改分支保护；无回执不宣称镜像完成。
- 没有新增守护进程或框架；构建串行、低优先级、锁定依赖，并做容量/内存预检。
- 入口不移动 `server-accepted`；该引用只由协调者在复核后用 ref-advance（compare-and-swap + fast-forward）移动。

## 1. prepare（构建并导出不可变 workspace，不部署）

```bash
python3 deploy/diy/server_release.py prepare \
  --source /root/hxy-diy-development/<worktree> \
  --sha <40位完整SHA>
```

- 校验 worktree clean 且 `HEAD == --sha`。
- 串行构建 diy-web 与 admin-react（`nice -n 19 npm ci` + `npm run build`），
  显式保留当前构建标志：读取 current 的 `admin-react/dist/staff-learning-build.json`
  决定 `VITE_STAFF_LEARNING_ENABLED`，构建后重写该 marker；客户 base path 记为 `/`。
- 导出 `<release-root>/workspaces/server-<sha12>-<epoch>/`（含 hxy-server、两个 dist、
  deploy 与 MANIFEST.sha256、build-report.json、evidence/），拒绝符号链接与重复 release id。

## 2. inspect（默认，只读）

```bash
python3 deploy/diy/server_release.py inspect --repo /root/hxy-diy-automation
```

输出 current、已准备 workspace、pending GitHub backup 记录与 `server-accepted` 状态；不构建、不部署。

## 3. acceptance 记录

`publish` 只接受精确 SHA 的协调者 acceptance 记录（不是任意 true 标志）：

```json
{
  "schema": "server-release-acceptance@1",
  "release_id": "server-<sha12>-<serial>",
  "source_sha": "<40位完整SHA>",
  "previous_release": "github-386b572ce599-43589601497",
  "manifest_sha256": "<workspace MANIFEST.sha256 的 sha256>",
  "evidence": [
    {"kind": "test", "path": "api.json", "sha256": "<证据文件 sha256>"}
  ]
}
```

`evidence` 中的文件必须实际存在于 `workspaces/<release-id>/evidence/`，非空且哈希一致。
缺失、失败、过期（previous_release 与当前 current 不符）或外来（source SHA 不符）证据均拒绝。

## 4. publish（显式部署一次）

```bash
python3 deploy/diy/server_release.py publish \
  --release-id server-<sha12>-<serial> \
  --acceptance /path/to/acceptance.json \
  --repo /root/hxy-diy-automation
```

- 先 reconcile：若 `releases/<id>` 已存在且 current 已指向它，返回 `already_deployed` 不重复派发；
  若存在但不一致则拒绝。
- 复核 source SHA、previous/current、manifest、evidence，再单次派发
  `deploy-production.sh`（沿用其 flock 锁，不嵌套加锁）。
- 部署后校验 stdout 的 `previous=` 与 current 指向，捕获竞争部署；成功后写
  `release-records/pending-github-backup-<id>.json` 并生成、验证本地 Git bundle。

## 5. server-accepted 引用（协调者专用）

```bash
python3 deploy/diy/server_release.py ref-init  --sha <评审基线SHA> --repo <repo>
python3 deploy/diy/server_release.py ref-show  --repo <repo>
python3 deploy/diy/server_release.py ref-advance --new <新SHA> --expect <当前SHA> --repo <repo>
```

ref-advance 要求 `--expect` 等于当前引用（compare-and-swap）且新 SHA 是当前的后代（fast-forward），
否则拒绝。本任务不移动该引用。

## 6. GitHub 异步备份

部署成功后生成的 pending 记录绑定精确 SHA，并由协调者的本机官方 GitHub API/GCM 通道在
仓库侧完成镜像；服务器侧只保留本地已验证 Git bundle 作为待备份期间的恢复副本。
没有 worker 时不要把 pending 记录写成“已调度”；无 GitHub 回执即视为 pending。
