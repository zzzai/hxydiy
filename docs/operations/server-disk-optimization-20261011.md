# 服务器磁盘优化记录：2026-10-11

任务：`OPS-SERVER-DISK-20261011`。生产根目录 `/root/hxy-diy-20260811`。本文记录实际操作与验证，长期维护规则见 [disk-maintenance.md](disk-maintenance.md)。

## 结果与授权边界

用户要求优化服务器磁盘，并单独批准：正式发布成功后，只清理本次重复上传包和解压工作区，保留失败现场、全部已安装版本、数据库与备份，不自动删除历史版本。

| 时点 | 使用率 | 可用字节 | 约合GB（十进制） |
| --- | --- | ---: | ---: |
| 开始 | 93% | 3150745600 | 3.15 |
| 最终，2026-10-11 18:04:15（Asia/Shanghai） | 82% | 7393202176 | 7.39 |

净增加4242456576字节，约4.24GB。根磁盘总41956249600字节；最终已用32756072448字节。任务期间另一窗口正常部署了#251，且备份和日志继续增长，因此净增加不是各项清理字节的简单加总。inode并非瓶颈。82%仍高于既有80%预警线，不能称容量风险彻底解除。

未删除已安装release、数据库、数据库备份、Docker卷、镜像、容器或手工/孤立工作区；未改历史保留数量、SSH公钥/强制入口、生产环境/凭据；没有重启Docker或业务服务，也未读取顾客手机号、健康报告或写选单、授权、改绑。

## 已执行的清理

1. 在生产双锁内执行 `docker builder prune --all --force --filter until=48h --keep-storage 536870912`，只清理过期构建缓存，保留512MiB。该步实际可用空间增加1442299904字节。没有执行image/container/volume prune，也没有设置自动构建缓存清空任务。
2. 历史工作区先只读预览，再按精确计划SHA执行：`bf37880ad5b72c2e921b6eedf8ef368cc1903da7d5253d4f9b1a516e2f17efbe`。27个超过7天、非current、无运行引用的CI工作区，经逐文件内容/大小/权限及完整安装MANIFEST验证后移除，内容521632833字节。每个对应安装release仍在；独有、失败/孤立、手工、近期及校验不符目录跳过。恢复来源记录在逐项输出，不删除整棵workspaces目录。
3. 仅移除 `/root/.npm/_cacache`、`/root/.npm/_npx` 并执行 `apt-get clean`，可用空间增加347127808字节。这些是可重新下载缓存；没有卸载软件、删除 `.npmrc`、源码或已安装依赖。
4. 3个未使用的VS Code服务版本先完整离机归档，核对远端/本地SHA、12207个归档条目的可读性和 `tar --diff` 源内容，再检查进程/文件/映射/参数/挂载引用后移除。保留最近两个服务版本、正在运行的CLI和全部扩展。
5. 稳定清理脚本安装后，对当前已成功发布版本 `github-369d90a33d91-38128752578` 执行一次实际收尾。完整路径、上传SHA、安装/工作区逐文件、MANIFEST、双锁及运行引用校验通过，只移除该版本的解压工作区、上传归档和校验侧文件，安装release仍完整保留。该步骤不是重新部署业务应用。

VS Code移除项：

- `Stable-04c0d99f4fb0d8afe6ce4f0c58e31e183ac3e4b1`
- `Stable-2242ebbb54efeeb0129e08e919e7e8d43033cd83`
- `Stable-7debcd0e2acdea1c52de81bf9ee1620444407dda`

保留 `Stable-2a59476c9bfcb90b3ddc372c36762471b7dfad1c` 与 `Stable-07f806f999227108933c2e30515b26eecc1fda74`。完整恢复归档移出临时worktree，位于 `C:/Users/gaoji/Documents/ChatGPT/hxy-diy-operations-backups/20261011-disk/vscode-unused-three-20261011.tar.gz`，648971590字节，SHA256 `ada67c0fd3332f80376e04f1022636ee94155c851f4a0066765caa66d007126d`；归档仍保留，远端临时重复归档已移除。恢复前需确认目标目录缺失、空间足够，在维护锁内从这份已校验归档恢复，不覆盖当前工具。

## 源码、安装与验证状态

- 实现：[PR #253](https://github.com/zzzai/hxydiy/pull/253)，HEAD `66eacc3fffa5e135b47ce1eb48c957c7defe1fe1`，合并 `f0a7670a161d268ade73073c70e2845e4211fb1c`。
- 本地52项：47通过、5平台跳过；隔离Linux 15项全部通过，包括POSIX符号链接、真实模式、当前/失败/不同内容/在用保护与发布调用顺序。`git diff --check`通过。
- 精确main [CI 38130054195](https://github.com/zzzai/hxydiy/actions/runs/38130054195)成功。CI不等于生产；本轮另执行了稳定工具安装及实际清理核验，没有触发业务应用部署工作流。
- 稳定安装在 `/root/hxy-diy-20260811/deploy/diy/`，来自合并提交的原始Git归档。锁内复核旧gateway哈希，编译/允许与拒绝命令检查通过，助手先安装、gateway最后原子替换。gateway保留root:root/0700，助手root:root/0600。
- 原gateway恢复副本：`/root/hxy-diy-20260811/operations/gateway-backups/20261011T100256Z-f0a7670/github-ssh-gateway.py`，SHA256 `b56d612d31910414cc75b67442a2bd2bdba750968f14e72dc93d8203ccc3aec3`，同目录保留安装回执。恢复需要维护锁和旧文件SHA验证，不修改authorized_keys。

安装文件SHA256：

| 文件 | SHA256 |
| --- | --- |
| `github-ssh-gateway.py` | `02e75c8946b6802b7bfa5fef2d852cda79a67c479d6916fc762f6d63269fc8fe` |
| `cleanup-published-inputs.py` | `7b39918fb234a93d1e93265996ebf6b66f31da9c2b6dc2b9dd7f607b74677a15` |
| `disk_maintenance.py` | `0cce8338d8b839d8633e9daa466691b75c8caefb4845318c57fe98dd4f08b150` |

真实当前release收尾已完成；完整“下一次GitHub发布→gateway触发收尾”事件尚未发生，不能冒充已现场验证。其调用顺序和失败跳过已有测试，稳定工具实际哈希及清理行为已核验。后续自动收尾只针对当次成功输入，校验失败保留，不自动扫除历史release。

## 生产证据

最终current：`/root/hxy-diy-20260811/releases/github-369d90a33d91-38128752578`，是另一窗口[PR #251](https://github.com/zzzai/hxydiy/pull/251)的正常业务发布。安装和实际收尾前后current及全部12个容器ID一致；9个运行、3个历史停止均保留，所有有健康检查的运行容器healthy，27个Docker卷保留。不能把这表述为整个任务时段没有任何容器变化：中间#251业务发布正常更新了DIY API。

`/`、`/admin/`、`/technician/` 和 `/api/v1/health` 均HTTP200，健康响应 `status=ok`、`service=hxy-customer-api`、`environment=production`；current完整MANIFEST有效。顾客实际主包 `/assets/index-BcOBP-YF.js` 被公网HTML引用，公网与安装SHA均为 `27cc0fe03e9d4cb07324fb2f9d339b17a66fd91b2a0003a10e3422e3445dd4e5`。这只是本次运维后可用性/版本验证，不替代微信现场的本人报告或业务验收。

`hxy-diy-monitor.timer`、`hxy-diy-backup.timer`、`tcm-webhook.service`、`tcm-check.timer`、`tcm-backup.timer` 继续active。既有容量阈值80%预警、90%严重、不足3GiB严重不改；未验证外部通知是否触达。DIY与主要业务容器既有10MiB×3轮转继续保留；旧 `hxy-api/hxy-db` 无限日志当前占用小，本轮不为其重建服务，下次相应系统维护另行处理。

本地证据根：`C:/Users/gaoji/.codex/worktrees/server-disk-optimization/hxy-diy/output/server-disk-20261011/`。其中 `workspace-plan.json`、`workspace-apply.log`、`build-cache-cleanup.log`、`download-cache-cleanup.log`、`vscode-cleanup.log`、`maintenance-installation.json`、`published-input-cleanup.log` 和 `final-verification.json` 记录实际结果。证据属于ignored运维输出，不作为业务源码提交；恢复归档另存稳定目录，不能随worktree清理。

## 留存风险与下一步

容量已恢复，但82%仍预警。已安装历史版本和数据库备份会继续增长；发布后收尾只减少重复输入，不能限制这些受保护数据的总量。历史release/备份归档与保留数量、异机备份以及磁盘扩容需要单独确认，不通过自动删除扩大本轮授权。后续窗口按本维护规则操作，不降低原3GiB发布门禁，也不因Docker“可回收”标签删除数据卷。

本文为操作后事实补录，只合并文档，不再部署业务应用。
