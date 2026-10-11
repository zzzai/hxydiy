# 发布输入与磁盘维护

范围：清理可验证的重复发布输入，不缩减已安装 release、数据库备份或 Docker 数据卷。维护过程不读取环境变量、凭据或顾客数据，不重启业务容器。

## 发布成功后的自动收尾

用户于2026-10-11批准：仅在正式发布成功后，清理该次重复上传包和解压工作区；保留失败现场、全部已安装版本、数据库和备份。

- GitHub SSH gateway 先完成原有备份、恢复演练、部署与公网 bundle 检查；成功返回后才调用稳定目录中的 `cleanup-published-inputs.py`。发布失败不会调用清理。
- 清理器重新获取 `.deploy.lock` 和 `.manual-deploy.lock`，确认 `current` 仍是本次完整 release ID；新发布抢先启动时跳过，不等待或干预新发布。
- 逐文件比较工作区与安装目录的内容 SHA256、大小和权限，并核对完整 MANIFEST。上传包实际 SHA256 必须匹配侧文件，上传目录不能有第三份未知文件。
- 路径仅允许 `workspaces/<本次ID>` 和 `incoming/<本次ID>`；目录、文件不得通过软链接越界，不得包含数据库/备份/密钥文件。已安装 release 和 backups 永远不是删除目标。
- 进程文件描述符、工作目录、可执行文件、映射、已知绝对路径参数以及容器挂载引用目标时保留输入。
- 任一检查失败都保留输入；清理失败只报告保留现场，不回滚已成功的业务版本。只有本次输入被处理，不自动处理历史版本。

稳定安装位置：`/root/hxy-diy-20260811/deploy/diy/` 下的 `github-ssh-gateway.py`、`cleanup-published-inputs.py`、`disk_maintenance.py`。从已合并的精确提交校验安装，保留原 gateway 的可恢复副本及文件权限；不要改 SSH 公钥、强制命令入口或生产环境文件。无需重新部署其他窗口的业务改动。

## 历史工作区：先预览后执行

`tools/operations/disk_maintenance.py` 与发布清理器共享实现。默认只预览；历史候选必须超过7天、非 current、完全重复且有有效已安装 MANIFEST。失败/孤立/手工工作区、独有文件、近期文件均跳过。

```bash
umask 077
python3 /root/hxy-diy-20260811/deploy/diy/disk_maintenance.py > /root/hxy-diy-20260811/tmp/workspace-plan.json
sha256sum /root/hxy-diy-20260811/tmp/workspace-plan.json
# Review the exact candidates and pass the independently approved full SHA256.
python3 /root/hxy-diy-20260811/deploy/diy/disk_maintenance.py --apply-plan /root/hxy-diy-20260811/tmp/workspace-plan.json --approved-sha256 <approved-sha256>
```

执行前整体复核全部候选，逐项删除前再核对 current、容器标识、运行引用与候选指纹。输出每个已处理目录及保留的恢复来源；部分失败不能称全部成功，不盲目重跑旧计划。

恢复时在生产锁内确认工作区目标不存在，再从记录的已安装 release 复制原输入内容。安装目录永久保留，因此可重建源文件；不保证重新压缩后的上传包与原 gzip 二进制逐字节相同。

## 其他占用

- 构建缓存：本轮仅清理超过48小时未使用的缓存，保留512MiB；不执行 Docker image/container/volume prune。此命令是人工维护，不新增定时自动删除。
- npm/apt：仅下载缓存可重新下载；不卸载已安装软件、不删除 `.npmrc` 或源码。
- VS Code：先检查实际运行引用、保留当前工具和最近两个服务版本；旧版本须完整离机归档、核对 SHA256/归档可读性及当前源内容后才移除。
- 日志：当前 DIY 与其他主业务容器已有10MiB×3轮转。旧 `hxy-api/hxy-db` 的无限日志本轮尚小，未重启/重建；下次该系统维护再确认轮转配置，不能为了释放小空间中断服务。
- 数据库卷、历史备份、TCM 数据、手工工作区、模型和其他项目均不根据“可回收”字样删除。历史 release/备份保留数量、异机备份和扩容需要独立决定。

既有 `hxy-diy-monitor.timer` 容量监测继续保留：80%预警、90%严重、不足3GiB严重。systemd状态记录不是负责人已经收到外部通知，不宣称告警触达已闭环。

## 验证

本地：`python -m unittest discover -s tests -p 'test_*.py'`。Linux隔离夹具补齐符号链接/真实文件模式覆盖；不得以 Windows 的跳过项冒充验证。维护后核对 `df`、current、容器ID与健康、公网首页/管理端/技师端及实际主包安装哈希；保护数据不得因本轮操作发生变化。实际操作记录另记 CURRENT-STATE 和 WORK-STATUS，脚本合并、生产安装与下一次真实发布触发分别记录。
