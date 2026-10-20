# 技师端订单价格契约 v1

状态：实现中
范围：`GET /api/v1/technician/tasks`（服务位）和 `GET /api/v1/technician/my-tasks`（我的服务，技师默认落地页）的只读价格展示；不改变下单、定价、会员核验、支付或服务状态。

## 1. 背景

技师端目前能看到服务项目名称，但看不到项目单价和订单合计。默认落地页 `/technician/today`（“我的服务”，读取 `/my-tasks`）和服务位页 `/technician/positions`（读取 `/tasks`）需要同一套价格口径。会员价和非会员价同时由 `SelectionSession.pricing_snapshot` 持久化；技师需要在开始/结束服务前核对顾客实际选择的项目和两种价格口径。

## 2. 响应

`/tasks` 的 `items[]`、`unassigned_items[]` 和 `/my-tasks` 的 `items[]` 增加可选对象 `pricing`，两个接口形状一致：

```json
{
  "pricing": {
    "store_total_cents": 19900,
    "member_total_cents": 15900,
    "member_saving_cents": 4000,
    "applied_price_type": "member",
    "lines": [
      {
        "line_index": 0,
        "name": "舒享精油 SPA",
        "quantity": 1,
        "unit_store_price_cents": 19900,
        "unit_member_price_cents": 15900,
        "store_line_total_cents": 19900,
        "member_line_total_cents": 15900
      }
    ]
  }
}
```

### 字段语义

- `store_total_cents`：非会员价合计（门店价口径）；
- `member_total_cents`：会员价合计；
- `member_saving_cents`：两者差额，非负；
- `applied_price_type`：`store` / `member` / `group`，仅表示本单记录使用的价格类型，用于 UI 标注；缺失或未知时为 `null`；
- `lines[]`：按 `pricing_snapshot.lines` 顺序返回，最多只包含价格展示所需字段；
- 快照中存在显式价格字段（含显式 0，例如赠送项目）时按快照返回；显式 0 是记录值，不视为缺失；
- `pricing` 为 `null` 的规则：
  - `/tasks`：无订单（空闲服务位）、冲突（同一服务位存在多个活动占用）；
  - `/my-tasks`：会话没有可用的持久化价格快照（无快照、或快照只有非价格字段且无正合计）时为 `null`，不返回伪造的 0；
- `/tasks` 既有行为保持不变；本次只把价格读取逻辑抽取为共享 helper，由 `/tasks` 与 `/my-tasks` 共用。

所有金额单位为分。接口不新增写操作，不返回顾客姓名、手机号、优惠券明细或其他个人信息。

## 3. UI 展示

- 价格展示口径以 `applied_price_type` 为准，不同时并列会员价和非会员价：
  - `member`：只显示会员价（逐项、合计、卡片摘要）；
  - `store`：只显示门店价（逐项、合计、卡片摘要）；
  - `group`：只显示团购价；当前后端快照未提供 group 金额时显示“团购价待确认”，不得用会员价或门店价替代；
  - `applied_price_type` 缺失或未知：显示“价格类型待确认”，不展示金额，避免误导。
- `/tasks` 服务位页：服务位卡片、未排座行、订单抽屉均按上述单一口径展示；
- `/my-tasks` 我的服务页（技师默认落地页）：任务卡片、订单详情同样按上述单一口径展示；
- 无 `pricing` 时完全降级为只显示项目名称，不显示 0 或空白价格列。

## 4. 兼容与降级

- 旧任务或无 `pricing_snapshot` 的会话：`/tasks` 保持既有返回兼容；`/my-tasks` 返回 `null`，前端回退为只看项目名称；
- 只读接口不改变服务位、订单或支付状态；
- `member_total_cents` 即使顾客当前不是会员也返回，便于技师区分两种价格；是否实际采用由 `applied_price_type` 标明；
- 不返回顾客姓名、手机号、优惠券明细或其他个人信息。

## 5. 验证

- 后端合同测试：
  - `/tasks`：已提交的普通服务位任务、未排座任务都返回会员价和非会员价；
  - `/my-tasks`：已排座任务返回会员价/非会员价合计和逐行价格；无快照、快照只有非价格字段时降级为 `null`；
  - 共享 helper 单测覆盖逐行缺字段回退、显式 0 与缺失的区分；
- 前端单测：金额格式化、会员/非会员标签、价格行读取；
- 前端生产构建通过；
- 不涉及迁移、权限变化或顾客端契约变化。

## 6. 变更记录

- 2026-10-20 v1.2：技师端按 `applied_price_type` 只展示本单实际价格口径；`member` 只显示会员价、`store` 只显示门店价、`group` 显示团购价（无金额则待确认）、未知类型不展示金额。接口仍返回两种价格供审计和降级使用。
- 2026-10-20 v1.1：`/my-tasks` 也返回 `pricing`；价格读取逻辑抽取到 `hxy-server/app/domain/technician_pricing.py` 供 `/tasks` 与 `/my-tasks` 共用，`/tasks` 行为不变；`/my-tasks` 无价格快照时严格返回 `null`。
