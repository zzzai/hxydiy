# 管理端经营分析契约

## 门店经营汇总

`GET /api/v1/admin/operations-summary` 仅对绑定当前门店的店长或绑定门店的历史 `admin` 开放；普通员工和未绑定门店的总部账号不得以该接口越过门店范围。

- 日期范围按 UTC 自然日筛选；开始日不得晚于结束日。
- `transactions` 仅统计该门店、该日期内已支付且未取消/退款的订单。
- `project_sales` 从这些订单的冻结 `items` 行快照聚合，返回最多五项 `project_id`、历史 `name`、`quantity` 与去重 `order_count`。
- `project_sales` 不返回顾客字段，也不分摊优惠券或组合加项的结算金额；它是已支付项目销量，不是财务结算报表。
- 跨店订单、未支付/退款/取消订单以及没有 `project_id` 的行不得进入该汇总。

## 2026-11-13 数据源与时区边界

- `period.timezone` 明确为 `UTC`；当前 `/admin/operations-summary` 不静默切换为北京时间自然日。品牌总览使用 `Asia/Shanghai` 的部分保持独立口径，跨报表比较前必须先确认时区。
- 新增 `data_sources`：`transactions=diy_orders`、`includes_external_pos=false`、`external_pos_name=智荟宝`，并明确实收不包括外部收银。
- 取消、过期、退款、退款驳回不计入实收；项目名来自订单冻结行快照，目录改名不回写历史。
- 没有受控支付/订单关联时，本汇总不得称为全店真实营收；页面显示该边界，不把 DIY 汇总和外部收银相加。
