# 三端统一：脚本等待，只读最终报告，失败才介入

适用于顾客端、管理端、技师端。工具进入同一仓库，不依赖某个窗口的聊天或本机绝对路径。

## 固定交付步骤

1. 保护现有改动，基于最新主干完成本次开发及本地验证，提交明确文件、推送分支并创建 PR。脚本不替你扩大提交范围。
2. 记录本次 PR 编号和完整 head SHA。用户已授权本次合并时，运行下面的后台命令；否则去掉 `-Merge`，脚本只等人工合并。
3. 只把 PID、报告路径交给用户，结束模型回合。Windows 隐藏后台进程自行等待（默认 45 秒一次、最多 60 分钟），不调用任何模型。
4. 下次需要结果时，只读本次 `report.json`；成功无需读 CI 全量日志。失败、超时或权限拒绝才打开报告中的 CI/部署链接，读失败步骤附近并处理。

```powershell
# 在任意一个已同步的本仓库 worktree 中运行；替换编号和完整 SHA。
pwsh -File tools/release/start-release-watch.ps1 -PullRequest 123 -Head <40位SHA> -Merge

# 已合并，只等待当前主干提交的 CI / 自动部署：
pwsh -File tools/release/start-release-watch.ps1 -Commit <40位main-SHA>
```

非 Windows 或前台执行：`python tools/release/watch_release.py --pr 123 --head <40位SHA> --merge`。
无需安装 Python 第三方库或 GitHub CLI；使用已有 Git Credential Manager 凭证，仅保存在内存，禁止把凭证写入命令、报告或仓库。

## 输出与安全边界

- 报告存放在 Git 公共目录下 `hxy-release-reports/<提交或PR及head>/report.json`，跨 worktree 防重复等待、按任务隔离；操作系统锁在进程结束时自动释放。报告原子替换，不覆盖代码或生产数据。
- `terminal=false`：仍在等待，不表示通过。`--once` 只读一次，进行中退出码为 2；成功/跳过/已被新主干取代为 0，需要处理的终态为 1。
- `deployment_succeeded`：精确 SHA 的 main push CI 与部署任务成功；这是 Actions 证据，不等同“当前生产仍是该版本”，也不是门店现场验收。
- `deployment_skipped`：部署任务明确跳过，不能写成已发布。`superseded`：main 已变化，不再等待或重发旧版本。失败、未知部署任务、检查缺失超时均不得宣称成功。
- 现有部署工作流继续负责 SHA 产物检查、服务器备份恢复演练、迁移拦截、Manifest、容器更新、健康检查和失败回滚。涉及现场交互或实时 current 核验仍按交付要求执行，不能因省 token 省掉验证。
- 生产记忆仍由实际发布负责人根据可验证报告及必要实时核对更新；脚本不自动把未知 current、备份或迁移信息写成事实。
- `-Merge` 仅允许同仓库、非草稿、main 目标、指定 head 的 PR；必需静态/三端/可信检查全部成功。可选 `AI PR Review` 必须已完成且为 success 或 skipped，failure 不放行，缺失继续等待。GitHub 合并 API仍执行分支保护，拒绝就停止。
- 通过本机已授权凭证合并会产生常规 push 事件，沿用 main CI → Deploy Production。不要依赖旧 Auto Merge PR 对 skipped AI 的处理，也不要使用 GITHUB_TOKEN 合并后假设会自动触发 push 工作流。
- 监控脚本不部署、不重跑失败工作流、不强推、不解冲突、不绕过门禁、不更改凭证或数据库；已有服务器发布脚本内部的健康重试/失败回滚不受影响。

## 零 token 的准确含义

脚本等待、状态归纳和 GitHub Actions 不调用模型。云端 AI 审查只有维护者设置 `ENABLE_CLOUD_AI_REVIEW=true` 且配置密钥才启用；跳过不代表已做 AI 审查。开发、设计判断、用户主动要求的 AI 复核及失败分析仍消耗 token，Actions 计算/网络也可能有费用。

正常等待无需 Codex 定时唤醒、心跳或新开任务；电脑需保持运行、网络连接，进程终止后可用同一命令重新等待。没有承诺自动通知到聊天窗口，报告是机器可读交接物。
