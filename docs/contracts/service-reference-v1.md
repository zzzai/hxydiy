# 服务参考标签契约 v1

状态：生产使用中  
数据结构版本：`schema_version=2`  
标签体系版本：`taxonomy_version=service_reference_v1`

## 数据职责

- `customer_reported`：顾客表达的重点、避让、力度、温度和可选原话。
- `technician_observed`：技师对本次服务是否合适的客观记录。
- `next_visit`：下次延续本次或到店再确认。
- `customer_confirmed`：顾客是否确认本次结构化服务参考。
- 展示文案可以优化，存储编码在同一 taxonomy 版本内不得改变含义。
- 结构化服务参考不得自动转换为普通运营标签。

## 编码

### 重点部位 `customer_reported.focus_areas`

| 编码 | 展示 |
|---|---|
| `neck_shoulder` | 肩颈 |
| `waist_hip` | 腰臀 |
| `legs` | 腿部 |
| `abdomen` | 腹部 |
| `feet` | 足部 |
| `full_relaxation` | 整体放松 |

最多 6 项，不允许重复。

### 避让部位 `customer_reported.avoid_areas`

使用 `neck_shoulder`、`waist_hip`、`legs`、`abdomen`、`feet`，不包含 `full_relaxation`。最多 5 项，不允许重复。

### 力度 `customer_reported.force_preference`

| 编码 | 展示 |
|---|---|
| `gentle` | 轻柔 |
| `medium` | 适中 |
| `strong` | 偏强 |

### 温度 `customer_reported.temperature_preference`

| 编码 | 展示 |
|---|---|
| `lower` | 偏低 |
| `medium` | 适中 |
| `higher` | 偏高 |

### 服务反馈 `technician_observed.service_feedback`

| 编码 | 展示 |
|---|---|
| `suitable` | 本次合适 |
| `better_after_adjustment` | 调整后更合适 |
| `adjust_next_time` | 下次需调整 |

### 下次建议 `next_visit.plan`

| 编码 | 展示 |
|---|---|
| `repeat_current` | 延续本次 |
| `confirm_on_arrival` | 到店再确认 |

## 写入约束

- 必须关联已完成服务，且技师只能记录本人完成的服务。
- 至少填写一项结构化内容；`quote` 最长 100 字。
- v2 的 `signals` 和 `note` 必须为空，不能混用旧版自由标签和备注。
- 后端拒绝未知字段、未知编码、重复数组项、医疗结论、联系方式、消费能力和人格评价。
- 写入必须带幂等键，并保留门店、顾客、技师、服务会话、来源、确认状态、确认时间和更正关系。

## 读取边界

- 管理角色可在本店范围读取完整历史和更正关系。
- 技师只可在活动服务中读取最近一次已确认、未被更正替代的安全摘要。
- 技师摘要不返回顾客原话、自由备注、人口属性、联系方式、创建人或精确确认时间。

## 当前实现与下一步

- 当前后端使用严格类型和白名单作为入库权威，技师前端内置同版本中文映射。
- 管理端虽然能读取原始 v2 记录，但尚未完成专用展示、筛选和聚合。
- 下一步由后端提供只读标签字典接口，管理端和技师端消费同一版本；在接口上线前，修改任何编码必须同时修改后端校验、前端映射、合同测试和本文件。
