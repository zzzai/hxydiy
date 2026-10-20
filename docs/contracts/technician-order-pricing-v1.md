# 技师端订单价格契约 v1

状态：实现中
范围：`GET /api/v1/technician/tasks`、`GET /api/v1/technician/my-tasks`、`GET /api/v1/technician/service-history` 的只读价格展示；不改变下单、定价、会员核验、支付或服务状态。

## 1. 背景

技师端目前能看到服务项目名称，但看不到项目单价和订单合计。会员价和非会员价同时由 `SelectionSession.pricing_snapshot` 持久化；技师需要在开始服务前核对顾客实际选择的项目和两种价格口径。

## 2. 响应

`GET /tasks` 的 `items[]`、`unassigned_items[]`，`GET /my-tasks` 的 `items[]`，以及 `GET /service-history` 的 `items[]` 增加同一可选对象：

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
- 无订单/冲突/价格快照缺失时 `pricing` 为 `null`，不伪造价格。

所有金额单位为分。接口不新增写操作，不返回顾客姓名、手机号、优惠券明细或其他个人信息。

## 3. UI 展示

- 服务位卡片：显示会员价/非会员价合计；
- 未排座行：显示会员价/非会员价合计；
- 我的服务：每个项目显示会员价和非会员价，并显示两种合计；
- 历史服务：同样显示项目价格和两种合计；
- 订单抽屉：
  - 每个项目行显示会员价、非会员价；
  - 显示“会员价合计 / 非会员价合计”；
  - 显示本单采用的计价类型；
  - 无价格时显示“—”，不显示 0 误导。

## 4. 兼容与降级

- 旧任务或无 `pricing_snapshot` 的会话：`pricing` 为 `null`，前端回退为只看项目名称；
- 只读接口不改变服务位、订单或支付状态；
- `member_total_cents` 即使顾客当前不是会员也返回，便于技师区分两种价格；是否实际采用由 `applied_price_type` 标明。

## 5. 验证

- 后端合同测试：已提交的普通服务位任务、未排座任务、本人正在服务的任务和本人历史都返回会员价和非会员价；没有可识别价格时 `pricing` 为 `null`，不把原始快照里的备注或无关金额带出；
- 前端单测：金额格式化、会员/非会员标签、价格行读取；
- 前端生产构建通过；
- 不涉及迁移、权限变化或顾客端契约变化。
