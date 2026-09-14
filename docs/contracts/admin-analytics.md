# 管理端经营分析契约

## 门店经营汇总

`GET /api/v1/admin/operations-summary` 仅对绑定当前门店的店长或绑定门店的历史 `admin` 开放；普通员工和未绑定门店的总部账号不得以该接口越过门店范围。

- 日期范围按 UTC 自然日筛选；开始日不得晚于结束日。
- `transactions` 仅统计该门店、该日期内已支付且未取消/退款的订单。
- `project_sales` 从这些订单的冻结 `items` 行快照聚合，返回最多五项 `project_id`、历史 `name`、`quantity` 与去重 `order_count`。
- `project_sales` 不返回顾客字段，也不分摊优惠券或组合加项的结算金额；它是已支付项目销量，不是财务结算报表。
- 跨店订单、未支付/退款/取消订单以及没有 `project_id` 的行不得进入该汇总。
