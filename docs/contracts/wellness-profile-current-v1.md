# 当前顾客画像契约 v1

状态：本地实现，未合并、未发布、未完成门店现场验收。

## 目的

`customer_profile_current` 是从服务参考原始记录投影得到的当前有效画像，用于后续服务连续性。它不是新的自由标签系统，也不是诊断、营销分层或健康评分。

## 输入与兼容

- 当前投影只消费 `schema_version=3`、`taxonomy_version=service_reference_v2` 且 `customer_confirmed=true` 的记录。
- `schema_version=1` 旧画像和 `schema_version=2 / service_reference_v1` 保持原路径只读，不自动升级或复制到当前画像。
- 未确认记录、`technician_observed`、`next_visit`、`quote`、`note` 和 `signals` 不进入当前画像。
- `service_related_context`、用药、孕产、健康相关自述和其他敏感信息在顾客侧独立授权能力发布前不进入当前画像。

## 可投影字段

| 原始路径 | 当前画像编码 | 多值 | 有效期 |
|---|---|---:|---:|
| `customer_reported.focus_areas` | `focus_area` | 是 | 180 天 |
| `customer_reported.avoid_areas` | `avoid_area` | 是 | 180 天 |
| `customer_reported.force_preference` | `force_preference` | 否 | 180 天 |
| `customer_reported.temperature_preference` | `temperature_preference` | 否 | 180 天 |
| `customer_reported.personal_context.age_band` | `age_band` | 否 | 365 天 |
| `customer_reported.personal_context.build` | `body_build` | 否 | 365 天 |
| `customer_reported.personal_context.height_band` | `height_band` | 否 | 365 天 |
| `customer_reported.work_lifestyle.occupation_contexts` | `work_context` | 是 | 180 天 |
| `customer_reported.work_lifestyle.sleep_quality` | `sleep_feeling` | 否 | 30 天 |
| `customer_reported.communication_consumption.decision_priorities` | `decision_focus` | 是 | 180 天 |

所有值继续使用 `service_reference_v2` 已发布稳定编码；中文文案只由字典接口负责展示。

## 当前画像行

每行包含顾客、画像编码、值键、值 JSON、可选部位维度、来源记录、首次和最近确认时间、确认次数、有效期、敏感等级、授权关联、字典版本和状态。

唯一维度为：

```text
customer_id + profile_code + profile_value_key + body_area_code + body_side
```

单值字段以最近一次已确认记录整体替换；多值字段以最近一次已确认数组整体替换。显式空数组清空该字段。任何角色不得直接编辑当前画像，必须通过原始记录更正后重建。

## 过期与读取

- `valid_until <= 当前时间` 的行状态为 `expired`。
- 默认读取只返回 `active` 且未过期行。
- 历史过期行可在权限允许的审计场景读取，但不能作为当前服务提示。

## 管理端接口

`GET /api/v1/admin/v2/users/{user_id}/customer-profile-current?include_expired=false`

- 仅 `manager`、`admin` 可调用。
- 先验证顾客与当前员工属于同一门店范围。
- 默认响应不返回敏感字段、顾客原话、联系方式、消费金额、创建技师或完整原始记录。
- 成功返回至少一行时写入 `manager_view_customer_profile_current` 审计，审计只保存编码和数量，不复制值。
