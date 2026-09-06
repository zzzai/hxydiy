# 养生行业顾客画像与复购数据体系设计

## 1. 目标与边界

荷小悦当前已有顾客、匿名浏览器身份、选单、订单、到店、服务反馈、技师服务参考、行为事件、运营标签和审计能力。最新 `origin/main` 已包含 `schema_version=3`、`taxonomy_version=service_reference_v2` 的扩展画像、字典接口和确认摘要；是否已发布生产必须由发布窗口实时核验，不能仅依据主干代码判断。

本设计的第一经营目标是提升顾客复购和下次服务体验。它建立以下闭环：

```text
服务原始记录 -> 顾客确认 -> 当前有效画像 -> 可解释计算特征
             -> 到店提示或复购行动 -> 行动结果 -> 下一次计算
```

已确认原则：

1. 只有顾客确认的信息进入长期画像。
2. 技师观察只属于当次服务，不自动成为顾客长期事实。
3. 同一浏览器匿名 ID 只代表同一浏览器上下文，不代表自然人身份。
4. 匿名历史只有在可信登录且顾客主动确认后才合并到会员档案。
5. 顾客自述、技师观察、系统事实和系统计算分开存储。
6. 原始事实只追加和更正，不覆盖历史。
7. 所有编码版本化；中文展示文案不作为统计主键。
8. 结构化服务参考与普通运营标签不得相互自动转换。
9. 0–1 阶段使用透明规则，不引入黑盒模型。

## 2. 数据分层

### 2.1 原始事实

原始事实记录每次服务真实发生的内容：顾客身份、门店、服务位、项目、技师、时间、顾客表达、技师观察、服务调整、服务结果、确认状态、字典版本和更正关系。误填时追加更正记录并引用原记录。

### 2.2 当前有效画像

当前画像是从顾客已确认记录中生成的快照，例如全局力度适中、右肩使用轻柔力度、左膝避让、沟通偏好安静。它是派生数据，不允许后台直接修改，并且必须可以从原始事实重建。

### 2.3 计算特征

计算特征包括最近到店天数、90 天服务次数、典型复购周期、周期进度、项目偏好度和偏好稳定度。每项必须保存计算窗口、证据数量、规则版本、计算时间和有效期。

### 2.4 运营分群

运营分群是对计算特征的可变映射，例如“接近复购周期”。它可以随规则变化，但不得反向修改事实、当前画像或特征。

## 3. 数据架构

### 3.1 复用现有表

- `users`：顾客主体。
- `browser_instances`：第一方浏览器身份。
- `selection_sessions`、订单、到店：交易与履约事实。
- `customer_profile_records`：追加式服务参考。
- `event_logs`：浏览与行为事件。
- `customer_tags`、`customer_tag_relations`：运营标签。
- `audit_logs`：关键操作审计。

### 3.2 当前画像表

新增 `customer_profile_current`：

```text
id, customer_id, profile_code, profile_value_json
body_area_code, body_side, source_record_id
first_confirmed_at, last_confirmed_at, confirmation_count
valid_until, sensitivity_level, consent_id
taxonomy_version, status, created_at, updated_at
```

唯一维度为 `customer_id + profile_code + body_area_code + body_side`。无部位含义时部位为空；部位级偏好优先于全局偏好。

### 3.3 计算特征快照表

新增 `customer_feature_snapshots`：

```text
id, customer_id, feature_code, feature_value_json
window_start, window_end, evidence_count, rule_version
calculated_at, valid_until, store_scope_json
```

保留历史快照以解释规则变化，实时服务页只读取最新有效快照。

### 3.4 授权表

新增 `customer_profile_consents`：

```text
id, customer_id, consent_type, purpose, data_categories_json
scope_json, consent_method, consent_text_version
selection_session_id, granted_at, revoked_at, expires_at, status
```

普通服务偏好长期保存、敏感健康相关服务参考长期保存、跨门店使用、营销触达必须分别授权。

### 3.5 身份合并记录

新增 `customer_identity_merge_records`：

```text
id, source_customer_id, target_customer_id
source_browser_instance_id, merge_reason, confirmation_method
consent_id, status, conflict_summary_json
merged_at, reverted_at, created_at
```

匿名主体合并后保留到目标顾客的别名关系，支持审计、去重和恢复。

## 4. 匿名身份与会员合并

首次扫码时创建匿名顾客和随机浏览器令牌，浏览器保存第一方令牌，数据库保存哈希。换设备或清除浏览器数据后创建新匿名身份，不做设备指纹或模糊识别。

合并必须同时满足：

1. 当前浏览器持有有效匿名令牌。
2. 顾客完成手机号验证码、微信或其他可信登录。
3. 系统展示待合并历史的脱敏摘要。
4. 顾客主动确认合并。

一次事务中锁定来源和目标顾客，迁移选单、订单、到店、评价、画像原始记录、可归属行为事件和运营标签，更新浏览器身份，按授权处理敏感信息，重建当前画像，加入特征待重算队列，并写合并审计。任何一步失败整体回滚。

偏好冲突时使用最近一次顾客确认值，历史证据全部保留；敏感字段冲突进入待顾客确认；无法证明属于同一顾客时保持两个身份独立。

## 5. 字典版本

- 数据结构：`customer_profile_schema_v4`
- 画像字典：`wellness_profile_v1`
- 身体部位：`body_area_v1`
- 复购计算：`retention_features_v1`

`schema_version=3`、`service_reference_v2` 是本设计的兼容基线。v4 对重叠字段继续使用 v2 已发布编码，只新增细分身体部位、部位状态、长期画像、授权和计算特征；`schema_version=1` 旧画像及 `schema_version=2`、`service_reference_v1` 继续只读兼容，不改写历史。

## 6. 画像字典

### 6.1 基础画像

全部选填，不是保存服务记录的前置条件。

| 编码 | 可选值 | 来源 | 有效期 |
|---|---|---|---|
| `age_band` | `18_24`、`25_34`、`35_44`、`45_54`、`55_64`、`65_plus` | 顾客确认 | 365 天 |
| `height_band` | `shorter`、`average`、`taller` | 顾客确认 | 365 天 |
| `body_build` | `slim`、`balanced`、`sturdy` | 顾客确认 | 365 天 |
| `hair_volume` | `less`、`medium`、`more` | 顾客确认 | 365 天 |

不保存技师猜测的精确年龄、身高和体重。

### 6.2 工作生活

| 编码 | 可选值 | 有效期 |
|---|---|---|
| `work_context` | `desk_work`、`standing_work`、`frequent_driving`、`physical_labor`、`family_care`、`freelance`、`retired`、`other` | 180 天 |
| `daily_posture` | `prolonged_sitting`、`prolonged_standing`、`frequent_head_down`、`frequent_bending`、`repetitive_hand_use`、`frequent_walking` | 180 天 |
| `exercise_frequency` | `rarely`、`weekly_1`、`weekly_2_3`、`weekly_4_plus` | 180 天 |
| `exercise_type` | `walking`、`running`、`fitness`、`ball_sports`、`swimming`、`cycling`、`yoga`、`other` | 180 天 |
| `sleep_feeling` | `good`、`average`、`poor` | 30 天 |
| `recent_fatigue` | `none_reported`、`mild`、`obvious`、`not_mentioned` | 30 天 |

来源只能是顾客明确表达，不从外貌、职业名称或单次行为推断。

### 6.3 身体部位

- 头面：`head`、`face`
- 颈肩：`neck`、`shoulder`
- 背腰：`upper_back`、`mid_back`、`lower_back`、`waist`
- 上肢：`upper_arm`、`elbow`、`forearm`、`wrist`、`hand`
- 躯干：`chest`、`abdomen`、`side_waist`
- 臀髋：`buttock`、`hip`
- 下肢：`thigh`、`knee`、`calf`、`ankle`、`foot`
- 整体：`full_body`

侧别使用 `left`、`right`、`bilateral`；无侧别含义时为空。

### 6.4 顾客主观感受

均展示为“顾客自述”：

```text
soreness_reported, distension_reported, pain_reported
numbness_reported, fatigue_reported, cold_feeling_reported
heat_feeling_reported, swelling_reported
sensitivity_reported, limited_motion_reported
```

每项关联部位、侧别、发生时间范围、当前状态和确认记录。

### 6.5 技师服务观察

```text
tightness_observed, stiffness_observed, hard_spot_observed
temperature_sensitive_observed, pressure_sensitive_observed
slow_relaxation_observed, quick_relaxation_observed
skin_reaction_observed
```

技师只能记录触感和服务反应。“摸到局部偏硬”不得转写成“结节”，“活动不便”不得转写成疾病诊断。观察默认只属于本次服务。

### 6.6 顾客自述相关情况

```text
previous_injury_reported, previous_surgery_reported
inflammation_history_reported, joint_condition_reported
muscle_strain_reported, spine_condition_reported
medication_reported, pregnancy_reported
postpartum_reported, other_condition_reported
```

结构为“类型 + 部位 + 侧别 + 状态 + 服务处理”。

状态：`recent`、`ongoing`、`recovering`、`historical`、`uncertain`。

服务处理：`focus`、`gentle`、`avoid`、`confirm_each_visit`、`no_special_handling`。

这里只记录顾客自述及其对本次服务的影响，不记录技师诊断、治疗判断或疗效承诺。

### 6.7 服务偏好

| 编码 | 可选值 |
|---|---|
| `force_preference` | `gentle`、`medium`、`strong`、`varies_by_area` |
| `temperature_preference` | `lower`、`medium`、`higher` |
| `pace_preference` | `slow`、`medium`、`faster` |
| `position_preference` | `supine`、`prone`、`side_lying`、`seated`、`needs_adjustment` |
| `duration_preference` | `shorter`、`standard`、`longer` |
| `movement_explanation` | `none_needed`、`key_steps`、`every_step` |
| `conversation_preference` | `quiet`、`light_conversation`、`likes_chatting` |
| `project_intro_preference` | `do_not_initiate`、`when_needed`、`open_to_intro` |

`varies_by_area` 必须至少关联一个部位级力度偏好。

### 6.8 服务过程与结果

| 编码 | 可选值 |
|---|---|
| `adjustment_type` | `increase_force`、`decrease_force`、`increase_temperature`、`decrease_temperature`、`change_position`、`change_focus`、`avoid_area` |
| `response_after_adjustment` | `better`、`no_clear_change`、`uncomfortable`、`not_reported` |
| `relaxation_response` | `quick`、`medium`、`slow`、`not_observed` |
| `subjective_effect` | `clearly_relaxed`、`somewhat_relaxed`、`neutral`、`uncomfortable`、`not_reported` |
| `overall_feedback` | `suitable`、`better_after_adjustment`、`adjust_next_time`、`not_reported` |
| `next_visit_plan` | `repeat_current`、`adjust_focus`、`confirm_on_arrival`、`none` |

服务结果每次追加，不形成永久不变的顾客属性。

### 6.9 消费与关系

技师只记录顾客明确表达的 `decision_focus`：`price`、`quality`、`environment`、`efficiency`、`service_continuity`。项目、技师、门店和时段偏好由真实服务行为计算。

不收集或推断收入、消费能力、人格、办卡意愿和“是否容易营销”。

## 7. 有效期

| 内容 | 规则 |
|---|---|
| 近期疲劳、睡眠感受 | 14 至 30 天，过期不显示为当前事实 |
| 当前疼痛或炎症相关自述 | 30 天，每次服务前重新确认 |
| 孕期、产后、正在用药 | 最长 30 天，每次服务前重新确认 |
| 皮肤、冷热或按压敏感 | 180 天 |
| 旧伤部位 | 365 天 |
| 手术史部位 | 历史事实保留，365 天后显示待再次确认 |
| 力度、温度、重点、避让 | 180 天 |
| 沟通偏好 | 365 天 |
| 工作生活 | 180 天 |
| 计算特征 | 每日刷新，按特征定义失效 |

过期不等于删除历史；过期信息不能继续作为当前偏好或自动行动依据。

## 8. 复购计算规则 v1

### 8.1 基础公式

```text
recency_days = 当前日期 - 最近一次完成服务日期
visit_count_30d/90d/365d = 对应窗口内完成服务次数
median_visit_interval_days = 最近最多 6 次有效到店间隔的中位数
cycle_progress = recency_days / median_visit_interval_days
project_affinity = 某项目完成次数 / 同窗口全部服务次数
technician_affinity = 某技师服务次数 / 同窗口全部服务次数
preference_stability = 某选项确认次数 / 同字段确认总次数
adjustment_rate = 需要调整次数 / 有明确反馈的服务次数
```

不足 3 次到店时不计算个人周期，使用“同门店 + 同首选项目”的脱敏总体中位数，并标记 `evidence_scope=cohort`。

### 8.2 稳定度与阶段

- 1 次确认：显示“上次选择”。
- 最近 180 天至少 2 次且一致率不低于 70%：较稳定偏好。
- 最近 180 天至少 3 次且一致率不低于 80%：稳定偏好。
- 最新确认冲突时采用最新值，稳定度重新计算。
- 过期后显示“历史参考，需重新确认”。

技师偏好少于 3 次不计算；占比不低于 60%为经常服务，占比不低于 80%且至少 4 次为稳定偏好。该结果不等同于顾客指定。

复购阶段：

```text
first_visit        完成 1 次服务
developing         完成 2 次，个人周期尚不稳定
approaching_due    周期进度 0.70 至 1.00
due                周期进度大于 1.00 且不超过 1.50
possibly_inactive  周期进度大于 1.50
stable_repeat      最近 180 天至少 4 次且间隔相对稳定
```

阶段只用于运营，不显示给技师，不改变服务待遇。

## 9. 采集触点

| 触点 | 系统 | 顾客 | 技师 |
|---|---|---|---|
| 首次扫码 | 创建匿名身份，记录门店与服务位 | 无需注册 | 无 |
| 浏览选单 | 记录浏览、选择、取消、提交 | 选择项目 | 无 |
| 服务前 | 调取上次有效参考 | 确认重点、避让、安全情况 | 简短询问 |
| 服务中 | 不录音、不持续采集 | 正常沟通 | 正常服务，不操作手机 |
| 服务后 | 带入项目和上次偏好 | 听取或查看摘要 | 20 至 30 秒点选 |
| 顾客确认 | 保存确认方式和文本版本 | 确认、修改、仅本次或拒绝 | 复述摘要 |
| 两次到店间 | 增量计算周期和偏好 | 无 | 无 |
| 下次到店 | 展示有效摘要与过期项 | 确认变化 | 只记录变化 |

## 10. 技师端 30 秒流程

服务结束后自动打开移动端抽屉或全屏页：

1. 沿用上次，约 3 秒：本次无变化、有变化、首次记录。
2. 身体图，约 8 至 15 秒：选择部位、侧别、顾客感受、技师观察和服务处理。
3. 服务偏好，约 5 秒：力度、温度、节奏、姿势和沟通；上次值必须点击“仍然适用”才视为本次确认。
4. 本次效果，约 5 秒：合适、调整后合适、下次需调整、未明确反馈。
5. 下次建议，约 5 秒：延续、重点调整、到店确认、暂无建议。

保存时选择“顾客已确认”或“尚未确认，仅保存本次”。敏感健康相关内容需要独立确认；未具备顾客侧独立确认能力时只作本次提醒，不进入长期画像。

## 11. 计算任务

顾客确认服务参考后同步更新当前画像，保证下次立即可用。订单完成、退款、画像确认、更正和身份合并时，把顾客加入待重算队列；每日只计算变化顾客。新服务会话建立时再对当前顾客轻量刷新。

0–1 阶段不建设独立数据仓库、复杂消息队列、向量数据库或模型服务。

## 12. 权限与展示

### 12.1 技师端

只在当前有效服务中显示上次确认偏好、有效重点和避让、每次需重新确认的提醒、信息日期及本次项目相关参考。不得显示手机号、消费金额、价值等级、复购阶段、营销标签、完整健康历史、其他门店自由备注或其他技师主观评价。服务结束或服务位释放后立即失去读取权限。

### 12.2 店长端

列表显示匿名/会员、最近到店、次数、典型周期、复购阶段、常用项目、时段、最近反馈和待确认状态。详情按服务时间线、已确认偏好、当前画像、计算依据、授权、更正和访问审计分区。敏感身体记录不直接出现在列表。

### 12.3 总部端

默认查看门店复购率、项目典型周期、偏好分布、服务调整率、匿名转会员率、服务参考确认率、画像覆盖率和过期率等聚合结果，不默认查看单个顾客敏感详情。

### 12.4 顾客端

逐步提供“我的服务参考”：查看、修改、撤回、仅本次使用、确认匿名历史合并、控制跨门店使用和单独管理敏感授权。

## 13. 异常处理

- 网络中断：本地保留草稿，恢复后使用原幂等键提交。
- 顾客未确认：保存当次事实，不更新长期画像。
- 偏好冲突：保留历史，当前画像采用最新确认值。
- 信息过期：保留历史，不作为当前有效信息。
- 匿名换设备：创建新匿名身份。
- 匿名转会员：顾客确认后幂等合并。
- 技师误填：追加更正，不覆盖原记录。
- 敏感字段无有效授权：拒绝进入长期画像。
- 计算失败：保留上一份成功快照并标记过期，不生成无依据分群。

## 14. 实施路线

1. 治理和契约：字典、来源、有效期、权限、合并规则及合同测试。
2. 身份和事实：补齐匿名转会员合并、冲突、审计与事务回滚。
3. 技师 30 秒画像：身体图、快选、沿用上次、断网草稿和幂等重试。
4. 当前画像与查看上次：投影、有效期、活动服务权限和到期确认。
5. 管理端与复购计算：时间线、计算依据、授权审计和每日增量任务。
6. 行动闭环：恢复偏好、接近周期待跟进、上次需调整提醒及结果记录。
7. 多门店分析：在字典、覆盖和身份准确性稳定后增量同步到分析库。
8. 可解释推荐：最后尝试复购周期、项目、时段和技师推荐，每次展示主要依据。

推荐发布顺序：

```text
字典与跨端契约 -> 匿名合并补全 -> 原始画像升级
-> 技师快记 -> 当前画像 -> 查看上次
-> 管理端展示 -> 基础复购计算 -> 单店灰度 -> 扩大门店
```

## 15. 指标

### 15.1 数据与体验

- 技师填写中位时间不超过 30 秒。
- 沿用上次不超过 10 秒。
- 无键盘可完成普通记录。
- 保存成功率不低于 99.5%。
- 重复提交产生重复记录为 0。
- 未确认记录进入长期画像为 0。
- 无证据计算标签为 0。
- 过期信息被当作当前事实为 0。
- 未授权敏感画像访问为 0。

### 15.2 经营结果

- 首次顾客 30/60/90 天二次到店率。
- 老顾客周期内回店率。
- 距典型周期的回店偏差。
- 有画像顾客中画像被实际复用的服务占比。
- 上次“下次需调整”顾客再次到店后的服务反馈。
- 匿名转会员率和确认合并率。

经营效果用同期对照或分批上线评估，不能仅凭上线前后变化断言因果。

## 16. 发布与验收

跨端契约变更在同一个 PR 中更新数据库迁移、后端、技师端、顾客确认入口、管理端、合同测试、`docs/contracts/` 和 `docs/TEAM-MEMORY.md`。

生产发布前必须完成：迁移和回滚验证、数据库备份与恢复、身份合并与回滚测试、门店隔离和权限审计、390×844 微信浏览器验证、弱网和幂等验证，以及单店灰度。自动化测试、线上健康和营业现场验收分别报告，不能混称为完成。

## 17. 暂不建设

- AI 诊断、疾病预测、疗效判断和健康评分。
- 收入、消费能力、人格和办卡意愿推断。
- 录音、自动语音分析、人脸识别和设备指纹。
- 自由标签直接进入连锁统一字典。
- 独立大数据中台、复杂消息队列、向量数据库和模型服务。
- 技师查看营销分群或顾客价值等级。
- 未经顾客确认把技师观察升级为长期画像。

## 18. 成功标准

1. 顾客身份连续且没有未经确认的错误合并。
2. 技师能在 30 秒内记录本次有价值的新信息。
3. 下次服务看到最新、有效、顾客确认且权限允许的服务参考。
4. 店长能根据可解释的到店周期采取适度复购行动。
5. 所有画像和计算结果都能追溯到原始事实、规则版本和授权状态。
6. 数据规模增长后可以增量同步和重算，无需清洗中文拼接标签或猜测历史含义。
