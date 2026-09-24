# 技师端服务生命周期 v1

## 目的与边界

本契约覆盖技师端（`/technician/`）对一条服务位占用的状态推进，以及 DIY 超时回收时的记录补写规则。

**不覆盖**：智慧宝负责的开沙发、开房、派钟、离位、清洁与物理资源释放。DIY 侧看板恒为只读，接口响应中的 `resource_control` 固定为 `external_read_only`。

技师端主动作**只有两个**：确认服务、服务结束。其余能力（会员核销、服务历史、顾客画像快记）均为记录型动作。

## 状态机

| 状态 | 技师端标签 | 可用主动作 | 说明 |
|---|---|---|---|
| `waiting_service` | 待确认 | `confirm` | 顾客已提交选单，技师尚未确认 |
| `in_service` | 服务中 | `finish` | 已确认，写 `actual_start_at` 与 `expected_end_at` |
| `post_service_present` | 已完成 | 无（仅画像快记） | 已写 `actual_service_end_at`，客人仍在场 |
| `conflict` | 待核对 | 无 | 同一展示区位存在多条活动占用，禁确认与结束 |

技师端**不存在「待评价」状态**。评价是顾客端动作（漏斗事件 `feedback_submit_success`），结果只在管理端 `/feedback` 呈现。

## 主动作与幂等

- `POST /api/v1/technician/occupancies/{id}/confirm`
- `POST /api/v1/technician/occupancies/{id}/finish`

幂等键设计：DB 层唯一键 `(store_id, idempotency_key)` 落在 `StateTransition`；重放必须同时匹配 `entity_id + action + actor_id + request_hash`，否则 `409 IDEMPOTENCY_KEY_REUSED`。并发撞键由 `IntegrityError` 回查兜底。幂等键绑定「当前服务位 + 动作 + 登录技师」，不得跨目标复用。

**未确认即结束被拒绝**：`waiting_service` 状态调用 `finish` 返回：

```json
{ "detail": { "code": "TECHNICIAN_SERVICE_NOT_CONFIRMED", "message": "请先确认服务，再结束服务" } }
```

后端与前端 `technicianActions()` 在此处口径一致：未确认只展示「确认服务」。

## 超时自动释放

阈值常量见 `hxy-server/app/domain/occupancy_release_policy.py`：

| 状态 | 触发 | 阈值 |
|---|---|---|
| `held` | 占位超时 | 10 分钟 |
| `waiting_service` | 未确认 | 60 分钟 |
| `in_service` / `post_service_present` | 预计结束时间超时 | +30 分钟 |

三条边界：

1. **只覆盖沙发**。`list_release_candidates` 的 `position_types` 默认 `("sofa",)`，房间与床位不进候选——这是有意设计：房间床位在 DIY 侧恒带智慧宝履约单，物理资源由智慧宝释放。
2. **有智慧宝履约单不释放**。`session.fulfillment_order_id` 非空即跳过。
3. 调度器每分钟扫 + 打烊扫，PostgreSQL advisory lock 保证单点执行。

## 自动释放时的结束时间补写

技师漏点「服务结束」时，占用被超时回收但 `actual_service_end_at` 为空，会导致该单不出现在技师服务历史（查询条件为结束时间非空）、服务时长无法计算、顾客画像快记入口随状态流失。

补写规则（仅作用于自动释放路径，管理端手工释放不适用）：

- 前置条件：状态属于 `{"in_service", "post_service_present"}` 且 `actual_start_at` 非空且 `actual_service_end_at` 为空；
- 优先取 `expected_end_at`（须不晚于释放时刻）；
- 缺失时回落为释放时刻 `now`；
- 审计 `detail.actual_service_end_at_source` 取值为 `auto_release_expected_end` / `auto_release_released_at`；
- 未确认即超时（`waiting_service`，未发生服务）不补写，该字段为 `null`。

### 并发与幂等

补写发生在释放同一事务内，不引入新的写入面。既有三重保护不变：候选行 `SELECT ... FOR UPDATE SKIP LOCKED`、`expected_versions` 乐观锁比对、调度器 advisory lock。补写本身幂等：二次扫描时该行已处于 `released`、不再进入候选集，且已存在的结束时间不会被覆盖。

## 关联实现与测试

- 实现：`hxy-server/app/domain/occupancy_release_policy.py`、`hxy-server/app/api/technician.py`
- 测试：`hxy-server/tests/test_occupancy_release_policy.py`、`hxy-server/tests/test_technician_portal_api.py`
