# 按项目服务记录 v1

状态：本地实现、专项回归与服务器隔离镜像验证通过，待合并发布。结构版本 `6`，字典版本 `service_record_v1`。

## 范围与兼容

首批适配招牌草本泡，按服务单项目快照编码 `hxy-xiaoqi-90` 识别；只有旧快照没有编码时才使用精确名称“招牌草本泡”。不修改项目名称、价格、时长或实际执行状态。其他项目保持 v5 记录与身体补充入口。v1–v5 历史不删除或迁移。

新记录复用 `customer_profile_records` JSON、门店、顾客、服务单、技师、确认和修订字段；无需数据库迁移。不进入当前画像投影、管理端聚合、算法训练或营销。

## 写入

沿用 `POST /api/v1/admin/v2/customer-profile-records` 和 `Idempotency-Key`。内外版本必须一致，旧 signals/note 不可混用。

`profile`：

- `template`：`herbal_signature_v1`；保留 `general_v1` 仅支持沟通与文字，当前 UI 不将其他项目切换到此模板。
- `water`：可选 `request=lower|suitable|higher`、`action=lowered|raised`、`feedback=suitable|still_unsuitable`。要求不代表已操作；不自动补反馈。
- `massage`：最多 3 条，`region=shoulder|neck|back|waist|abdomen|arm|leg|foot`，`side=left|right|both|unspecified`。同一部位与侧别唯一。至少有 request、action、feedback 一项；反馈可空。
- 按摩 `request=lighter|stronger|longer|avoid`；`action=lighter|stronger|longer|avoided`；`feedback=suitable|still_unsuitable`。
- `heat=too_hot|suitable|end_early` 为单次记录的明确反馈；先后变化与实际处理写入 `heat_note`，不把其当长期温度偏好。
- `communication=quiet|chat` 只记录顾客表达。
- `service_note`、`heat_note` 各最多 200 字，沿用已有隐私与诊断式内容拦截。
- `recording_outcome=no_additional_notes` 不得同时包含内容或顾客确认，不表示满意或清除历史。

字典由 `GET /api/v1/technician/service-record-options` 提供；前端只保存稳定编码。

## 权限与更正

仅在岗且已绑定技师的账号，针对本店本人完成、审计可核对、顾客与服务单匹配的服务写入。管理端不得代填新版。

v6 允许 `correction_of_id` 指向同门店、同顾客、同服务单、同技师、同创建账号的 v6 记录，并要求原因；锁定原记录检查，已有更正则返回 409。原记录不可覆盖，更正不增加服务次数。原 v1–v5 更正权限不扩展。

相同幂等键与载荷重试返回同一记录；内容变化生成新键。权限或状态拒绝不清空表单。

## 读取

- 本人服务历史增加 `own_record_id`，用于查看与更正。
- `GET /api/v1/technician/service-records/{id}/versions?page=1` 仅本人同门店同创建账号可读，每页 20 条，返回 `has_more`。提供同一次服务的旧版本、本人文字和回填任务，不提供顾客联系方式。其他账号返回 404。
- 活动服务位仍使用原 `service-reference` 接口、原门店和顾客关联。仅最近已确认且未被更正的记录进入服务前参考；v6 通过验证后的编码生成 `service_lines`，绝不下发补充文字。日期与“本店技师记录”标明来源。本次须重新询问。
- 匿名记录跟随服务端顾客主体；本轮不改变设备身份或合并规则。
- 管理端对 v6 仅返回版本与已有记录元数据，不返回部位、文字、完整载荷或更正原因。管理运营能力不在本轮扩展。

## 验收

真实 HTTP 验证保存、重试、字段与版本拒绝、项目匹配、顾客归属、管理端拒写、本人更正和保留原版本、其他技师安全读取以及失效服务位拒绝。浏览器验证真实 React 组件的失败保留与同键重试；接口模拟不等于生产或微信真机验收。
