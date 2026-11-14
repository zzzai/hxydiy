# 会员消费/余额空表迁移发布准备（2026-11-14）

## 授权与范围（仅准备，未部署）

- 用户已明确授权：在真实生产备份与隔离恢复核验通过后，仅创建 4 张空表并正常部署；本授权仅限 Alembic 修订 `20261114_member_consumption`。
- 四张精确新表：`membership_consumption_batches`、`membership_consumption_bills`、`membership_consumption_lines`、`membership_balance_snapshots`。
- 旧表/旧数据不可变：不修改任何旧 member/card/wallet/order/price 表或数据；不导入来源历史账单；不刷新余额；不恢复暂停的 15 卡批次。
- 新表保持为空；不导入任何真实数据。
- 生产迁移验证尚未执行，本文件不声称已部署。

## 变更

- `deploy/diy/deploy-production.sh` 在 `approved_migrations` 显式白名单中新增 `20261114_member_consumption.py`；未知/移除迁移拒绝、备份/恢复、rehearsal 迁移、健康/回滚门禁全部保持不变，无通用绕过开关。

## 保护

无生产 DDL、无真实数据导入、无余额写入、无旧数据修改、无 15 卡恢复。

## 待办（总控后续步骤）

- 真实生产备份 + 隔离恢复核验；受保护生产指纹；正常手动部署流程；部署后独立生产核验。
