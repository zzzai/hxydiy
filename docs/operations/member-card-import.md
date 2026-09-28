# 本店来源卡安全导入

## 本批能力与未完成边界

脚本 `hxy-server/scripts/import_member_cards.py` 在服务器项目的 `hxy-server/` 目录以模块运行。默认只预览，不读取美管加，不充值、不扣款、不发赠送，不覆盖现有昵称、登录身份、会员周期或DIY钱包。手机号仍须顾客完成现有短信验证才能登录本人账号。

本金余额是导入记录时点的来源值，`observed_at` / API `recorded_at` 是记录时间，不是外部最新消费时间。当前DIY没有来源卡本金扣款链路，不能覆盖智慧宝消费。重复导入相同资料无变化；余额、期限、状态变化或卡归属冲突会整批拒绝，不静默覆盖。

## 私有输入与预览

由受控导出转成JSON，另准备授权19人手机号白名单（一行一个）。两份文件及数据库备份必须放仓库外，限制为操作账号可读，不能提交Git或聊天。日期必须由真实原始日期按门店时区明确转成带时区ISO时间，不从文件修改时间猜测；相对最近消费时间、性别、消费汇总均不导入。

输入结构（只展示虚构结构，不提供真实名单）：

```json
{
  "source": "mgj_export",
  "store_code": "verified-target-store-code",
  "cards": [{
    "phone": "13800138000",
    "source_card_id": "original-card-id",
    "card_name": "荷小悦会员卡",
    "source_card_type": "储值消费卡",
    "started_at": "2026-09-01T00:00:00+08:00",
    "expires_at": null,
    "balance_cents": 100,
    "allow_cross_store": false,
    "status": "active"
  }]
}
```

以上单人示例不能用于生产；CLI强制完整19人白名单完全匹配。卡唯一键为目标门店编码与原始卡ID的SHA256，避免保存原始卡号。金额必须是整数分；赠金、债务不当作本金，不虚构消费订单。`status` 必须经源系统或有据人工核实为 `active` / `disabled`，表格无此字段时不能默认所有卡在用。

```bash
python -m scripts.import_member_cards /private/member-cards.json --phones-file /private/authorized-phones.txt
```

年度权益名称与源“储值消费卡”类型冲突时默认拒绝，包括预览。只有用户确认按年度名称和原始起止时间识别后才能加 `--confirm-annual-name-mapping`；年度卡缺真实到期日或期限超过原始一年均拒绝。不是按导入日续一年。

## 写入与可恢复要求

执行前核实服务器版本包含迁移 `20260928_membership_cards`，完成目标数据库备份、SHA256验证及隔离恢复演练；脚本只验证文件存在及哈希，不证明备份属于该库或可恢复，恢复演练仍由发布流程负责。

```bash
python -m scripts.import_member_cards /private/member-cards.json --phones-file /private/authorized-phones.txt --confirm-annual-name-mapping --apply --backup-file /private/verified-database-backup.dump --backup-sha256 VERIFIED_SHA256
```

必须先取得映射确认，以上不是当前执行授权替代物。脚本在同一事务写新增身份/卡与审计；异常回滚，报告只有计数和新增卡ID，不含手机号、原始卡号或密钥。记录执行版本、备份哈希和报告到私有运维资料；提交后核对19人绑定、每人卡种/期限/余额、门店范围并二次预览应为0新增。已有用户资料和财务事实必须不变。

提交前失败依赖事务回滚；提交后若需恢复，先停相关写入并沿已验证数据库备份恢复流程评估，不能自动删顾客或覆盖后续业务。报告中的新增卡ID供定向核对与受审计权益撤销；本脚本不提供删除用户或自动回滚生产入口。

## 尚待选择的人工余额更新方式

1. 定期重新导出，受控核对差异后由独立的审计更新命令登记来源卡余额与记录时间；目前脚本对差异只拒绝，尚不提供该更新命令。
2. 后台逐卡登记来源余额，必须包含核对人员、依据、更新时间和审计；当前只读“权益说明”，不提供此写入口。

两者都不创建DIY扣款、充值或赠送，并非实时同步。更新频率和负责人尚未确定，不自动选择。外部联调恢复前，不能把这些快照作为“当前外部余额准确”的承诺；实际19人导入尚未执行。
