# DIY 日常备份、容量与健康检查

范围：仅 `/root/hxy-diy-20260811` 和 `hxy-diy-db`。不清理全机Docker，不触碰其他系统，不依赖模型唤醒。当前为待安装方案，安装事实另记 CURRENT-STATE / WORK-STATUS。

## 数据保护

`tools/operations/production_ops.py backup` 与发布使用同一 `.deploy.lock`，至少预留3GiB后才导出数据库；每日一次02:10（门店时区）运行。数据库只读导出，恢复到随机命名的独立临时数据库，成功后删该临时库，不恢复到生产库。恢复失败不更新latest成功记录，保留失败partial文件供私有诊断。备份/报告权限0600、目录0700。日志不打印令牌、数据库内容或顾客信息。

备份仅数据库，不声称覆盖媒体对象、服务器配置及灾备全景。备份在同一数据库容器恢复可读，不等于另一机器的恢复能力。没有自动删除历史备份/发布/工作区；保留策略与异机目的地需明确后另执行。

## 监控与处理

每5分钟检查：公网health为production/ok、磁盘80%预警/90%严重及不足3GiB、最近每日备份26小时内且恢复已验证/实际文件SHA一致。状态保存 `operations/status.json`，退出1预警、退出2严重，systemd日志保留失败信号。最近失败也写私有报告。失败状态不是生产宕机的同义词，按issues处理。

systemd检测和日志信号不等于负责人已经收到通知。外部通知收件渠道须单独配置/验证；当前不擅自给真实手机号发短信，也不写外部Webhook。异机备份和实际负责人确认前不能称“灾备/运营已闭环”。

## 安装与核验

从合并后的精确提交部署这五个文件，保留已安装版本再替换，不改业务容器。脚本安装到 `/root/hxy-diy-20260811/operations/production_ops.py`，四个unit文件安装到 `/etc/systemd/system/`。

```bash
systemd-analyze verify /etc/systemd/system/hxy-diy-backup.service /etc/systemd/system/hxy-diy-backup.timer /etc/systemd/system/hxy-diy-monitor.service /etc/systemd/system/hxy-diy-monitor.timer
systemctl daemon-reload
systemctl enable --now hxy-diy-backup.timer hxy-diy-monitor.timer
systemctl start hxy-diy-backup.service
python3 /root/hxy-diy-20260811/operations/production_ops.py check
```

先做真实隔离恢复并核实latest SHA、timer下次运行及失败分支。本地单测仅验证脚本行为，不能当成生产数据库备份已完成。停止任务使用 `systemctl disable --now` 对应两个timer，不删除备份。模型只读最终短报告，不循环检查。
