# 经营分析数据源与 UTC 边界（2026-11-13）

- PR #489 合并 `c04cc7a1986c6d8de2032640f8759de6c59560c4`；CI 43377980123 success；Deploy 43378482044 success；current `github-c04cc7a1986c-43378482044`。
- `/admin/operations-summary` 新增 `period.timezone=UTC` 和 `data_sources`，页面增加数据源提示；不改变交易筛选和历史数值。
- 生产门店经理只读核验返回 UTC、DIY 订单、不含智荟宝、退款/取消排除和“非全店真实营收”边界；无业务写入。
- 无迁移；回退应用版本即可，历史订单/价格/支付不动。
- 外部收银受控关联和真实财务口径仍需另行确认。
