# BR-08 优惠券与 SCRM 自动化 PRD

关联：[README](README.md)、[customer-operations](customer-operations.md)
优先级：P1（当前页面不可达，P0 可达性）
当前实现：基础 CRUD 页面存在，业务闭环不足

## 1. 执行摘要

优惠券和自动化必须服务门店复购，而不是做一堆发不出去的规则。首版先保证：能创建、能审核、能定向发放、能核销、能统计、能停止，并且所有触达合规。

## 2. 问题与目标

- 优惠券页面有，但导航不可达；
- 券的适用范围、叠加、门槛、有效期不明确；
- 发放没有人群/门店范围；
- 核销与订单/结算未打通；
- 自动化没有触发条件、执行日志、失败重试；
- 触达可能违反顾客授权。

目标：

1. 券生命周期完整；
2. 发放对象可控；
3. 核销可对账；
4. 自动化可观测、可停止、可回滚；
5. 触达有授权和频控。

## 3. 角色与范围

| 角色 | 券模板 | 发放 | 核销 | 自动化 |
|---|---|---|---|---|
| 总部 | 创建/审核/全品牌 | 按人群/门店 | 跨店查看 | 创建/启停/审计 |
| 店长 | 查看/申请本店券 | 本店定向发放（授权） | 本店核销 | 查看本店执行 |
| 店员 | 查看 | 无 | 核销（授权） | 无 |
| 顾客 | 领取/使用 | — | — | 接收需授权 |

## 4. 业务对象

### CouponTemplate

```text
id, name, type: cash / discount / gift / package,
scope: brand / store / project / category,
threshold_cents, discount_cents / discount_rate,
max_discount_cents, valid_from, valid_to,
total_quota, per_customer_limit,
stackable, status: draft / review / active / paused / expired,
created_by, approved_by, version
```

### CouponIssue

```text
id, template_id, customer_id, store_id, status: issued / used / expired / revoked,
issued_at, used_at, order_id, source, operator
```

### Automation

```text
id, name, trigger: event / schedule / segment,
conditions, actions[], status: draft / active / paused,
frequency_cap, quiet_hours, created_by, updated_by
```

### AutomationRun

```text
id, automation_id, trigger_ref, status: queued / success / failed / skipped,
error, started_at, finished_at, affected_customer_id
```

## 5. 状态机

### 券模板

```text
draft → review → active → paused → expired
                     └→ archived
```

### 券实例

```text
issued → used
       → expired
       → revoked
```

### 自动化

```text
draft → active ⇄ paused
active → archived
```

规则：

- 已发放券不因模板暂停而失效（可配置）；
- 券过期由系统任务处理；
- 撤销需原因并审计；
- 自动化暂停立即停止新触发，不撤回已执行动作；
- 自动化执行必须幂等。

## 6. 核心流程

### 6.1 发券

1. 总部创建模板；
2. 审核通过并设置预算/配额；
3. 选择人群/门店/顾客；
4. 生成券实例；
5. 通知顾客（需授权）；
6. 核销/过期。

### 6.2 核销

1. 顾客到店出示券码；
2. 系统校验门店、项目、门槛、有效期、使用次数；
3. 锁定券，创建结算优惠；
4. 支付/结算完成后标记 used；
5. 失败释放锁。

### 6.3 自动化

1. 创建规则：触发、条件、动作、频控；
2. 测试发送；
3. 启用；
4. 触发执行，写 run 日志；
5. 失败重试/告警；
6. 暂停/归档。

## 7. 硬规则

- 优惠金额不能超过订单金额；
- 券不可重复使用；
- 同一模板每人限领可配置；
- 叠加规则必须显式，不允许隐式叠加；
- 自动化触达必须有顾客授权；
- 频控和免打扰时间必须生效；
- 自动化动作必须幂等，重复事件不重复发券；
- 所有发放/核销/撤销/触达写日志；
- 预算超限时停止发放并告警。

## 8. 权限与审计

- 券模板创建/审核/预算总部；
- 店长只能按授权发放本店券；
- 核销需店员/店长权限；
- 自动化动作涉及顾客隐私需审计；
- 批量发放必须审批并记录人群定义。

## 9. 指标

- 发券量、领取率、核销率、带来的订单/GMV；
- 券成本、ROI；
- 自动化触发/成功/失败/跳过；
- 触达退订率、投诉率；
- 预算使用率。

## 10. 验收标准

- [ ] 优惠券页面在导航可达且权限正确；
- [ ] 模板创建→审核→发放→核销→统计闭环；
- [ ] 核销校验门店/项目/门槛/有效期；
- [ ] 自动化有触发、动作、执行日志、失败重试；
- [ ] 触达有授权、频控、免打扰；
- [ ] 所有发放/核销可审计；
- [ ] 预算超限停止发放。

## 11. 当前实现差距

- `/coupons`、`/automation` 已可从总部/品牌管理员导航进入；
- 总部已提供“操作门店”选择器，优惠券/自动化操作按选中门店执行；
- 已实现管理端向本店顾客发放已上架优惠券：每人限领校验 + 审计；优惠券列表已展示发放、未用、已用和使用率；仍缺批量发放、预算和核销明细；
- 无预算和审批；
- 已实现规则执行日志：动作、顾客、成功/失败、失败原因、时间；尚未做全局日志筛选和失败重试；
- 与订单/结算未打通；
- 顾客触达授权模型未建立。

## 12. 非目标与开放问题

非目标：首版不做复杂营销画布/多波次。

🔵 OQ：优惠券预算由总部还是门店承担？
🔵 OQ：自动化首版支持哪些触发（评价后/生日/久未到店）？
🔵 OQ：企微触达是否需要顾客明确同意？
🔶 假设：首版只做定向发券+简单自动化，不做全渠道营销。
