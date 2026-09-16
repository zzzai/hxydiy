# 服务参考 v4 跨端契约

状态：本地实现，待 CI、合并与发布

数据结构版本：`schema_version=5`

标签体系版本：`taxonomy_version=service_reference_v4`

## 1. 目的与边界

本契约为技师端人体点位记录提供唯一的数据定义。记录表示顾客在本次服务中主动提到的身体相关情况及技师经确认后采用的服务处理，只用于本店服务连续性。

它不是诊断、病历、健康评分、顾客价值等级或营销标签。不得据此自动推荐治疗、判断疾病、差别定价、自动营销或跨店传播。

## 2. 兼容规则

- 新写入固定使用 `schema_version=5`、`taxonomy_version=service_reference_v4`。
- `schema_version=1` 至 `4` 继续只读兼容，不迁移、不覆盖、不补猜缺失字段；写接口拒绝这些历史版本。
- v5 新写入只允许服务连续性字段：沟通方式、重点/避让部位、力度、温度、本次实际调整、当次反馈、下次安排、身体条目和受限本人补充。年龄、体型、职业、作息、消费偏好、家庭与收入等旧画像维度不属于 v5，也不应由技师端写入。
- v5 允许技师更正本人同门店、同顾客、同一次已完成服务的记录：更正只追加新版本并要求说明原因，原记录保留；已被更正的记录不可再次更正。管理端、其他技师和 v1–v4 历史均不得更正。
- 中文文案可以优化，稳定英文编码在同一 taxonomy 版本内不得改义。
- 未识别版本必须安全降级为“存在历史服务参考，请到店确认”，不得直接展示原始 JSON。

## 3. 写入结构

```json
{
  "schema_version": 5,
  "taxonomy_version": "service_reference_v4",
  "customer_reported": {
    "communication_preference": "quiet",
    "body_service_notes": [
      {
        "region": "shoulder",
        "side": "right",
        "context": "long_term_discomfort_mentioned",
        "current_state": "occasional_discomfort",
        "session_handling": "lighter",
        "reconfirm_next_visit": true
      }
    ]
  },
  "technician_observed": {
    "service_adjustments": ["pressure_lighter"],
    "service_note": "仅本人回看时需要的补充",
    "recording_outcome": null
  },
  "customer_confirmed": true
}
```

`body_service_notes` 为可选数组，最多 3 条。同一记录中 `region + side` 必须唯一。每条五个字段均必填，不接收空字符串、未知编码或额外字段。

`communication_preference` 仅接受顾客明确表达的 `quiet`（希望安静）、`chat`（愿意聊天）或 `explain_before_action`（希望先沟通），是服务方式事实，不得由技师根据一次聊天、沉默或印象推断。

`technician_observed.service_adjustments` 为最多三项、不可重复的本次实际动作：`pressure_lighter`、`pressure_stronger`、`pace_slower`、`temperature_lower`、`temperature_higher`、`focus_area`、`avoid_area`、`end_early`。它是下次服务前可见的安全摘要，不等同诊疗判断。

`technician_observed.service_note` 是最多 200 字、仅记录技师本人历史可见的补充，不是顾客原话，也不作为跨技师交接。不得记录泛化画像、诊断结论或营销判断。`recording_outcome="no_additional_notes"` 表示本次没有新增服务信息，不能与任何标签、补充文字、身体条目或顾客确认同时提交。

## 4. 身体点位字典

### 4.1 部位 `region`

| 编码 | 展示 | 可用侧别 | 人体面 |
|---|---|---|---|
| `head` | 头部 | `center` | 正、背 |
| `neck` | 颈部 | `center` | 正、背 |
| `shoulder` | 肩部 | `left`、`right` | 正、背 |
| `chest` | 胸部 | `center` | 正 |
| `abdomen` | 腹部 | `center` | 正 |
| `upper_back` | 上背 | `center` | 背 |
| `mid_back` | 中背 | `center` | 背 |
| `lower_back` | 下背 | `center` | 背 |
| `side_waist` | 侧腰 | `left`、`right` | 正、背 |
| `upper_arm` | 上臂 | `left`、`right` | 正、背 |
| `elbow` | 肘部 | `left`、`right` | 正、背 |
| `wrist` | 腕部 | `left`、`right` | 正、背 |
| `hand` | 手部 | `left`、`right` | 正、背 |
| `hip` | 髋部 | `left`、`right` | 正 |
| `buttock` | 臀部 | `left`、`right` | 背 |
| `thigh` | 大腿 | `left`、`right` | 正、背 |
| `knee` | 膝部 | `left`、`right` | 正、背 |
| `calf` | 小腿 | `left`、`right` | 正、背 |
| `ankle` | 踝部 | `left`、`right` | 正、背 |
| `foot` | 足部 | `left`、`right` | 正、背 |

前端显示的左右以顾客本人身体左右为准，不以技师观看方向为准。后端必须校验 `region + side` 是否属于表中合法组合。

### 4.2 顾客自述情况 `context`

| 编码 | 展示文案 |
|---|---|
| `previous_injury_mentioned` | 顾客提及曾受伤 |
| `post_procedure_recovery_mentioned` | 顾客提及术后恢复中 |
| `recent_discomfort_mentioned` | 顾客提及近期不适 |
| `long_term_discomfort_mentioned` | 顾客提及长期不适 |
| `skin_sensitivity_mentioned` | 顾客提及皮肤敏感 |
| `reconfirm_requested` | 情况需到店确认 |

不得新增肩周炎、滑膜炎、腰肌劳损、结节、炎症或其他疾病/诊断名称作为结构化编码。

### 4.3 当前状态 `current_state`

| 编码 | 展示文案 |
|---|---|
| `currently_uncomfortable` | 当前仍有不适 |
| `occasional_discomfort` | 偶尔不适 |
| `no_current_discomfort` | 目前无明显不适 |
| `needs_reconfirmation` | 当前情况需再确认 |

### 4.4 本次处理 `session_handling`

| 编码 | 展示文案 |
|---|---|
| `avoid` | 本次避开 |
| `lighter` | 本次减轻力度 |
| `normal_after_confirmation` | 确认后正常进行 |
| `observe_and_reconfirm` | 本次观察，下次再确认 |

`session_handling` 只描述本次服务动作，不表示治疗、康复或疗效。

### 4.5 下次确认 `reconfirm_next_visit`

- 类型为布尔值。
- v5 首期必须为 `true`；后端拒绝 `false`。
- 每次新服务开始前都要重新询问，不能直接沿用为当前身体事实。

## 5. 数据来源与确认

- `context` 和 `current_state` 来源只能是顾客明确表达。
- `session_handling` 是技师与顾客确认后的本次服务处理。
- `customer_confirmed=true` 仅表示技师已向顾客复述本次结构化摘要并获得确认。
- 未确认记录可以作为当次追加事实保存，但不得进入当前画像、下次直接沿用或管理端运营统计。
- 不提供身体状况自由文本字段；既有 `quote` 继续执行诊断词和敏感内容拦截，且不得进入安全摘要。
- 补充文字只返回记录技师的本人历史；管理端、其他技师的下次服务摘要和当前画像均不返回或投影该文字。

## 6. 接口职责

### 技师端字典

`GET /api/v1/technician/service-reference-taxonomy`

返回 v5 版本、部位与合法侧别、情况、当前状态、本次处理及中文文案。前端不得维护另一份会独立演化的业务字典。

### 技师端写入

`POST /api/v1/admin/v2/customer-profile-records`

服务端必须校验：登录角色、当前技师、门店、服务归属、服务状态、版本、白名单、数量、唯一点位、顾客确认和幂等键。越权统一按既有安全策略返回，不暴露其他门店或其他顾客是否存在。

### 管理端读取

管理端沿用门店隔离的画像历史只读接口，但只返回服务方式、重点/避让、力度、温度、本次实际调整、当次反馈、下次安排及“服务前再确认”提醒。身体部位、身体自述、私人文字、原话，以及年龄、职业、消费等历史画像维度均不得进入管理端网络响应、列表、搜索、普通运营标签或导出。

## 7. 查看上次与匿名顾客

- 会员或已可信登录顾客：仅返回本店最近一条已确认、未被更正且权限允许的安全摘要。
- 匿名顾客：仅在当前服务仍绑定同一服务端匿名顾客主体时返回；浏览器随机标识只能辅助归属，不能证明自然人身份。
- 换设备、清除浏览器数据或无法证明身份连续时，不合并、不猜测，显示“暂无可确认的上次记录”。
- 身体条目在技师摘要中统一降级显示为“身体情况：服务前再确认”，不返回部位详情、情况、原话或诊断式文本。
- 匿名历史只有在顾客可信登录并主动确认合并后，才可按身份合并契约归入登录主体。

## 8. 当前画像与分析

v5 身体条目、交接补充文字与无新增完成结果首期不写入 `customer_profile_current`，不进入计算特征、复购标签、算法训练集或自动营销。未来若要进入长期画像，必须另行增加敏感信息授权、有效期、撤回、更正、跨店范围和顾客侧查看能力，并发布新契约版本。

允许统计的仅为不含正文和具体部位的流程指标：打开、完成、失败、耗时分桶和下次确认动作。不得记录疾病名称、自由文本或单个顾客身体详情到埋点。

## 9. 合同测试要求

- v5 合法 payload 可写入并按白名单读取；v1 至 v4 历史继续兼容但新写入必须拒绝。
- v5 写入携带年龄、职业、消费倾向、家庭、收入、作息或其他非服务连续性字段必须拒绝；管理端读取历史记录也不得回传这些字段。
- 未知版本、未知编码、非法侧别、重复点位、超过三条、缺字段和额外字段均拒绝。
- `reconfirm_next_visit=false` 拒绝。
- 诊断式自由文本继续拒绝，敏感正文不进入安全摘要和审计。
- 未确认记录不进入当前画像；v5 身体记录也不进入当前画像。
- 跨店、非本人服务、非活动或非本人完成的服务写入拒绝。
- 管理端和技师端读取均符合门店、服务归属与最小展示原则。

## 10. 发布条件

业务实现、字典接口、合同测试、本文件、`docs/TEAM-MEMORY.md` 和相关 workstream 必须在同一个 PR 更新。生产发布后才能更新 `docs/CURRENT-STATE.md` 与 `docs/WORK-STATUS.md` 为已发布事实。自动化通过、PR 合并、生产发布与门店现场验收必须分别报告。
