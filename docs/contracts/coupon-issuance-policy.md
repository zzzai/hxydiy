# 顾客发券策略暂停

2026-09-05 用户决定：移除匿名顾客送券引导，暂时停止新增发券策略。

- 后端 `COUPON_ISSUANCE_ENABLED` 默认 `false`，暂停新客自动赠券、主动领券、分享赠券与邀请奖励。
- `GET /api/v1/coupons/templates` 返回空列表；已登录顾客调用 `POST /api/v1/coupons/claim` 返回 409，错误码 `COUPON_ISSUANCE_PAUSED`；匿名调用继续返回 401。
- `POST /api/v1/coupons/claim-share` 返回 `granted: false`，不会新增券记录。
- 报价不再返回 `kind: coupon` 的登录引导；会员价差提示保持原有规则。
- 顾客端停止详情页领券引导，并忽略旧服务端的券类提交前提示，提交路径继续正常工作。
- 已发券、券模板及审计数据保留；我的券查询、原有券有效期、结算使用与门店活动价格保持原规则。
- 恢复策略需要同步后端开关与顾客端引导，不能只重新发布券模板。

已通过 PR #23 合入主干，并随 `manual-8912faf-20260905-3` 发布生效；后续状态以 CURRENT-STATE 的实际发布记录为准。
