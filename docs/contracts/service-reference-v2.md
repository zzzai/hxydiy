# 服务参考 v2 跨端契约

更新时间：2026-09-05
状态：本地实现，尚未发布生产或完成门店验收

## 版本、接口与边界

- 外层及 `profile` 内层必须同时为 `schema_version=3`、`taxonomy_version=service_reference_v2`。
- 技师写入 `POST /api/v1/admin/v2/customer-profile-records`；字典读取 `GET /api/v1/technician/service-reference-taxonomy`；管理端经 `GET /api/v1/admin/v2/users/{user_id}/customer-profile-records` 在既有员工授权和门店范围内只读展示。
- 管理端不得新增、更正或删除 v3，不得复制到普通标签、搜索索引或算法特征。`quote` 默认折叠，不进入统计或安全摘要。
- 内容仅作到店服务参考，不构成医疗建议。健康、用药等只能记录顾客自述，每次服务前须重新确认。

## 稳定编码

| 字段 | 稳定编码 |
| --- | --- |
| `customer_reported.personal_context.age_band` | `18_24`, `25_34`, `35_44`, `45_54`, `55_64`, `65_plus` |
| `customer_reported.personal_context.build` | `slim`, `balanced`, `sturdy` |
| `customer_reported.personal_context.height_band` | `shorter`, `average`, `taller` |
| `customer_reported.work_lifestyle.occupation_contexts` | `desk_work`, `standing_work`, `frequent_driving`, `physical_labor`, `family_care`, `freelance`, `retired`, `other`（最多 2 项） |
| `customer_reported.work_lifestyle.sleep_quality` | `good`, `average`, `poor` |
| `customer_reported.service_related_context.contexts` | `long_term_condition`, `recent_discomfort_recovery`, `skin_sensitivity`, `medication_mentioned`, `pregnancy_postpartum`, `other_reconfirm`（最多 1 项） |
| `customer_reported.service_related_context.quote` | 最多 100 字顾客自述；禁止诊断、治疗结论、联系方式、消费能力及人格评价 |
| `customer_reported.focus_areas` | `neck_shoulder`, `waist_hip`, `legs`, `abdomen`, `feet`, `full_relaxation`（最多 6 项） |
| `customer_reported.avoid_areas` | `neck_shoulder`, `waist_hip`, `legs`, `abdomen`, `feet`（最多 5 项） |
| `customer_reported.force_preference` | `gentle`, `medium`, `strong` |
| `customer_reported.temperature_preference` | `lower`, `medium`, `higher` |
| `technician_observed.session_response.relaxation` | `quick`, `gradual`, `tense` |
| `technician_observed.service_feedback` | `suitable`, `better_after_adjustment`, `adjust_next_time` |
| `next_visit.plan` | `repeat_current`, `confirm_on_arrival` |
| `customer_reported.communication_consumption.decision_priorities` | `price`, `quality`, `environment`, `efficiency`, `fixed_technician`, `fixed_time`（最多 6 项） |
| `customer_reported.communication_consumption.budget_preference` | `value`, `balanced`, `experience`, `unexpressed` |

字典接口是编码到中文文案的权威来源。客户端提交稳定编码；未知或重复编码由服务端拒绝。

## 来源、确认与可见范围

- `customer_confirmed=true` 时来源为 `both` 并记录 `confirmed_at`，表示技师已复述并获确认；`false` 时来源为 `service_observation` 且无确认时间，只表示本次观察。
- `customer_reported` 是顾客表达；`technician_observed` 是本次服务观察；`next_visit` 是下次建议，不是预约、诊断或承诺。展示必须使用服务端的 `source`、`customer_confirmed`、`confirmed_at`，不得自行推断。
- 管理端：授权员工仅可读取当前门店关联顾客的完整历史；原话默认折叠。
- 技师当前服务：仅本人所在门店活动服务位的服务端安全摘要；技师本人历史：仅本人明确归属的已完成服务，未关联旧服务只返回计数。
- 安全摘要只含白名单结构化值：重点/避开部位、力度、温度、职业场景、放松反应、服务反馈、下次建议、决策关注、预算偏好。禁止 `quote`、`note`、电话、身份、价格、收入资产负债、自由文本及其他嵌套值。
- 决策关注与预算偏好只用于沟通准备，禁止差别定价、消费能力推断、用户分层或自动营销。

## v1/v2 兼容与发布补证

- `schema_version=1` 旧画像继续按原 `profile` / `signals` / `note` 只读展示；不得自动升级或复制为 v3。
- `schema_version=2` + `service_reference_v1` 继续由既有读取和安全摘要路径兼容；不得改写为 v3。
- 新写入仅用 v3 单一载荷，`signals=[]`、`note=""`；各版本追加保存，不覆盖历史。
- 本任务不更新 `CURRENT-STATE.md` 或 `WORK-STATUS.md`。实际发布窗口须在服务器验证后补记备份/迁移、Manifest、release/current、健康检查、权限穿透、移动端及门店验收事实。
