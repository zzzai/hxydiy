# BR-02 到店选单、订单、结算与退款 PRD

关联：[README](README.md)、[service-position](service-position.md)、[admin-membership-closure-prd.md](../admin-membership-closure-prd.md)
优先级：P0
当前实现：部分（选单、订单、结算列表已有；双事实/详情/退款闭环不完整）

## 1. 执行摘要

把“顾客选了什么、门店如何履约、最终如何收钱”分成三个清晰事实：**选单**、**服务履约**、**财务结算**。三者通过明确关联字段连接，任何页面不得用其中一套数据冒充另一套。

## 2. 问题与目标

### 已确认问题

- 移动端订单只读，但桌面端仍可人工确认/开始/结束；
- 到店选单和订单收入可能各算一套；
- 结算列表缺状态全集、分页、详情、退款证据；
- 加选、改选、取消缺少完整变更历史；
- 超时由系统处理，但系统规则不透明。

### 目标

1. 每个履约事实有唯一来源；
2. 店长/技师能看懂“现在是什么状态、下一步谁做”；
3. 财务能从结算追到订单、服务、退款、操作人；
4. 异常不丢，不靠人记忆。

## 3. 角色与范围

| 角色 | 选单 | 服务履约 | 结算/退款 |
|---|---|---|---|
| 顾客 | 创建/提交/取消（未确认前） | 查看进度 | 查看支付结果 |
| 店长 | 本店只读 + 异常处理 | 本店查看、异常介入 | 本店查看；退款需授权 |
| 技师 | 本人服务只读 | 开始/结束本人服务 | 不可见金额操作 |
| 总部 | 跨店查看 | 跨店查看 | 跨店对账、退款审批 |
| 系统 | 超时关闭/通知 | 状态推进/超时提醒 | 支付回调/对账（P1） |

## 4. 业务对象

### 4.1 SelectionSession（选单）

关键字段：

```text
id, customer_id, store_id, status, submitted_at, confirmed_at,
needs_position_assignment, position_id, items[], addon_changes[],
fulfillment_order_id, total_amount_cents, source, created_at, updated_at
```

### 4.2 ServiceOrder（履约订单）

```text
id, store_id, selection_session_id, customer_id, status,
items[], original_amount_cents, discount_amount_cents,
paid_amount_cents, payment_status, paid_at,
technician_id, position_id, service_started_at, service_ended_at,
completed_at, cancelled_at, cancel_reason, created_by
```

### 4.3 SettlementRecord（结算）

```text
id, order_id, store_id, status: pending / paid / refund_pending / refunded / closed / exception,
method, amount_cents, paid_at, refunded_at, operator, evidence[], audit_refs[]
```

### 4.4 变更记录

所有加选、改选、取消、改价、退款都必须追加不可变变更记录：

```text
change_type, before, after, reason, actor, created_at
```

## 5. 状态机

### 5.1 选单

```text
draft → submitted → confirmed → in_service → completed
  └→ cancelled（顾客未确认前 / 店长异常取消）
  └→ expired（系统超时）
```

规则：

- `submitted` 后不允许顾客直接改项目，只能发起变更请求；
- `confirmed` 必须绑定服务位和履约订单；
- 超时未开始由系统判定并生成异常，不允许店员手工“点一下确认”绕过；
- 取消必须写原因和操作来源。

### 5.2 履约订单

```text
pending_payment → paid → confirmed → in_service → pending_checkout → completed
        └→ cancelled
        └→ refund_pending → refunded
```

状态推进只允许：

| 动作 | 谁 | 前置 |
|---|---|---|
| 支付成功回调 | 系统 | pending_payment |
| 开始服务 | 技师/系统 | confirmed 且绑定服务位 |
| 结束服务 | 技师 | in_service |
| 提交结算 | 系统/店长异常 | 服务结束 |
| 退款申请 | 店长 | paid/completed |
| 退款通过 | 总部授权 | refund_pending |
| 取消 | 顾客未支付/店长异常 | 未开始服务 |

## 6. 核心流程

### 6.1 到店选单→服务

1. 顾客提交选单；
2. 系统通知店长/前台；
3. 店长安排服务位；
4. 系统创建履约订单并关联；
5. 技师开始服务；
6. 技师结束服务；
7. 系统生成结算记录；
8. 顾客评价。

### 6.2 加选

1. 服务中技师/店员添加加项；
2. 系统生成待确认变更，不直接改已支付金额；
3. 店长确认或顾客确认（按金额阈值）；
4. 生成价差支付/补记；
5. 写变更记录。

### 6.3 退款

1. 店长发起，选择原因、金额、证据；
2. 校验原订单、结算、已核销权益；
3. 进入 refund_pending；
4. 总部审批；
5. 系统执行退款或登记线下退款；
6. 写退款凭证与审计。

## 7. 硬规则与不变量

- 一个选单最多关联一个履约订单；
- 一个履约订单最多一条有效结算记录；
- 实收金额 = 支付金额 - 已退款金额；
- 已退款金额不得超过支付金额；
- 已核销的会员权益不自动回退，需人工确认；
- 金额统一用整数分存储；
- 时间统一 UTC 存储，界面按 Asia/Shanghai 展示；
- 任何状态变更必须带 actor、source、timestamp；
- 系统超时任务必须幂等，重复执行不能重复取消/重复通知；
- 不允许前端直接传入目标状态，必须调用动作接口。

## 8. 权限与审计

- 店长可看本店订单详情，不可跨店；
- 技师只能看本人被分配的服务；
- 退款/改价/取消必须审计前后值、理由、证据；
- 总部跨店查询必须记录操作日志；
- 敏感字段（手机号、支付流水）按最小必要脱敏。

## 9. 指标

- 提交选单数、确认率、取消率、超时率；
- 平均确认时长、平均服务时长；
- 加选率、加选金额占比；
- 实收、退款、净收入；
- 结算异常数；
- 订单收入与结算记录对账差异。

## 10. 验收标准

- [ ] 选单确认后自动绑定履约订单，且两套数据总额一致；
- [ ] 移动端只读契约与桌面端动作契约一致；
- [ ] 订单详情能追到顾客选择、追加项、支付、退款、操作记录；
- [ ] 结算支持状态全集、分页、筛选、导出（P1）；
- [ ] 退款必须具备原因、证据、审批、审计；
- [ ] 超时任务幂等，重复执行不改变结果；
- [ ] 任何状态动作无权限时返回明确错误；
- [ ] 所有金额按分计算，前后端无浮点误差。

## 11. 当前实现差距

- 桌面 Orders 页面已改成只读结算列表，但后端仍保留 checkout/check-in/complete 等 legacy 动作接口，需要收口或加异常授权门；
- 已实现 `selection_sessions.fulfillment_order_id` 一对一关联；结算列表展示选单号、选单金额和关联状态；
- 已实现选单/订单对账检查：缺选单、缺订单、状态不一致、金额不一致；
- 工作台已展示近 30 天对账异常汇总，并可跳转异常队列；对账差异已持久化为工作项，支持同步、处理说明、关闭和审计；总部品牌总览已提供跨店待处理异常视图；已实现责任人指派、SLA 截止、确认处理和逾期提示；仍缺定时自动同步和升级通知；
- 已实现结算详情抽屉、分页、订单号搜索、全状态筛选、状态历史和退款调整；退款凭证附件仍待扩展；
- 加选确认链路未统一为变更记录；
- 退款只有“登记线下退款”，没有审批和凭证模型；
- 订单详情缺完整变更时间线；
- 订单/选单列表时间筛选与分页能力不足（店长移动端已补 7 天，桌面仍需）。

## 12. 非目标与开放问题

非目标：首版不接真实支付通道，不自动执行线上退款。

🔵 OQ：桌面端是否保留人工确认？建议仅异常授权，需运营确认。
🔵 OQ：退款审批人是店长/区域/总部哪一级？
🔵 OQ：会员权益核销后退款是否允许回退？
🔶 假设：首版支付继续线下/外部，系统只登记结算事实。
