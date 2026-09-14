# 管理端年度会员闭环接口契约

本契约只覆盖店长管理端与服务端；顾客端继续负责本人动态码和新设备绑定，技师端继续只消费动态码，后台不得用手机号直接给予会员价。

## 权限与数据范围

- 以下写操作均要求已登录的 `manager`，普通员工与跨门店请求返回拒绝或不存在。
- 所有命令使用服务端的当前时间、店长门店和数据库锁；前端不得传入任意价格、周期起止时间或服务资格结论。
- 支付记录仅保存渠道、脱敏尾号或人工收据号，不保存截图或完整非人工支付流水。

## 周期命令

| 命令 | 请求 | 约束 |
| --- | --- | --- |
| `POST /admin/v2/users/{user_id}/membership/enroll` | `payment_channel`、`payment_reference`、`rights_confirmed=true` | 服务端生成年度周期和起止时间。|
| `POST /admin/v2/users/{user_id}/membership/renew` | 同开通 | 仅旧周期到期前 90 天内；新周期从旧到期瞬间开始，状态为 `scheduled`。|
| `POST /admin/v2/users/{user_id}/membership/cancel` | `cycle_id`、`reason`、`refund_disposition` | 未用赠送变 `voided`；已用权益不回退。|
| `POST /admin/v2/users/{user_id}/membership/recover` | `cycle_id`、`reason`、`idempotency_key` | 仅已取消周期；同一幂等键只恢复一次并写审计。|

## 赠送服务行核销

`POST /admin/v2/selection-sessions/{session_id}/annual-gift/redeem`

请求体必须包含 `cycle_id`、`service_line_id`、`idempotency_key`。服务端在同一事务中锁定选单、顾客、会员周期和服务行；仅接受当前门店、已确认且已绑定顾客的选单，以及未开始的一项单次服务行。服务行还必须同时满足：项目已发布、属于当前门店、当前有效门店价不高于 9900 分、无任何加项或收费选项。

成功后服务端将该服务行标记为年度赠送、将应收价冻结为 0、把权益从 `available` 改为 `used`、记录服务行和审计，并在关联账单仍未收款且未结算时同步账单。相同 `idempotency_key` 和同一服务行可安全重试；不同幂等键或不满足资格的请求不得改价或消耗权益。

`POST /admin/v2/selection-sessions/{session_id}/service-lines/{service_line_id}/cancel`

请求体为 `reason`。仅允许取消未开始服务行；服务端保留服务行取消事实、从未收款账单移除该行并重新冻结报价。若该行占用的年度赠送所属周期仍为 `active`，权益回到 `available`；已退款/取消而作废的权益不因服务行取消重新开放。

## 审计与验收

核销、服务行取消、开通、续费、取消和异常恢复都写入审计。合同测试至少验证店长权限、门店范围、99 元上限、无加项、幂等重试、取消释放，以及取消周期后不重新开放赠送权益。
