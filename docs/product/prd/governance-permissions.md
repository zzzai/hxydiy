# BR-10 权限、工作区、员工账号与审计 PRD

关联：[README](README.md)、[store-lifecycle](store-lifecycle.md)、[technician-workforce](technician-workforce.md)
优先级：P0
当前实现：基础角色/工作区/授权可用；死页与细粒度权限缺口

## 1. 执行摘要

连锁后台的安全边界由三件事组成：**谁**（员工）、**能进哪个工作区**（scope）、**能做什么**（capability）。三者必须由后端统一判断，前端菜单只做提示，不能作为权限边界。

## 2. 问题与目标

- 页面配置/优惠券/自动化有页面但导航不可达；
- 总部/门店/品牌 scope 组合下部分菜单永远不可见；
- 前端按钮隐藏与后端权限可能不一致；
- 员工停用/改角色后令牌未立即失效；
- 审计缺少前后值、原因、关联对象。

目标：

1. 登录返回明确的工作区/能力；
2. 后端每个写接口都有权限和 scope 校验；
3. 导航与 capability 单一来源；
4. 关键操作可追溯到人、时间、前后值和理由。

## 3. 角色与工作区

```text
Staff
  id, name, phone, status: active / disabled / resigned
  roles[]: brand_admin / hq_operator / store_manager / store_staff / technician
  assignments[]: {scope_type: brand / region / store, scope_id, role}
  technician_id?
  credentials_version
```

规则：

- 一个员工可以有多个工作区；
- 登录先选工作区，再进入对应端；
- 店长必须有有效 technician_id；
- 角色与 scope 组合决定菜单和能力；
- 前端不得仅靠 localStorage 角色判断。

## 4. Capability 模型

最小能力集：

```text
store.read / store.write / store.lifecycle
catalog.read / catalog.write / catalog.publish
order.read / order.operate / order.refund
position.read / position.operate
customer.read / customer.sensitive / customer.export
review.read / review.followup
staff.read / staff.write / staff.role
analytics.store / analytics.brand / analytics.export
coupon.read / coupon.issue / coupon.redeem
automation.read / automation.write
audit.read
```

后端返回当前工作区 `capabilities[]`；导航按 capability 过滤。

## 5. 导航与死页规则

- 每个导航项必须绑定 capability；
- 有页面但无 capability 的，不能显示；
- 有 capability 但无页面的，必须补页面或移除入口；
- 当前 `/page-content`、`/coupons`、`/automation` 存在可达性问题，必须作为 P0 修复；
- 深链访问无权限时显示明确 403 页面，不回退首页。

## 6. 员工账号生命周期

```text
invited → active → disabled / resigned
```

规则：

- 邀请链接一次性、有有效期；
- 激活需验证手机号/密码；
- 停用/离职立即提升 credentials_version，令牌失效；
- 角色变更需重新登录或刷新 capability；
- 不允许删除员工，保留历史关联；
- 店长/技师绑定变更需审计。

## 7. 审计

审计对象：

- 登录/登出/失败；
- 权限/角色/scope 变更；
- 价格/目录/页面发布；
- 订单状态/退款/改价；
- 顾客敏感信息查看/导出；
- 门店状态/配置变更；
- 自动化启停/批量触达。

审计字段：

```text
actor_staff_id, scope, action, entity_type, entity_id,
before, after, reason, request_id, ip, created_at
```

硬规则：

- 审计只追加，不修改/删除；
- 敏感值脱敏；
- 导出/批量操作必须审计；
- 审计查询需要独立权限。

## 8. 核心流程

### 8.1 邀请员工

1. 管理员创建员工；
2. 分配角色/工作区；
3. 发送邀请；
4. 员工激活；
5. 登录选工作区；
6. 后端下发 capability。

### 8.2 改角色/停用

1. 管理员选择员工；
2. 修改角色/scope/状态；
3. 填写原因；
4. 后端校验不能移除最后一个总部管理员；
5. 写审计；
6. 立即失效令牌。

## 9. 指标

- 活跃员工/工作区数；
- 无权限访问次数；
- 邀请激活率；
- 令牌失效延迟；
- 审计覆盖率；
- 敏感信息查看次数。

## 10. 验收标准

- [ ] 导航项全部有 capability 来源；
- [ ] 死页在正确权限下可达；
- [ ] 无权限深链显示 403，不泄露数据；
- [ ] 写接口全部后端校验；
- [ ] 停用/离职令牌立即失效；
- [ ] 不能移除最后一个总部管理员；
- [ ] 关键操作审计含前后值/理由；
- [ ] 店长工作区必须绑定技师。

## 11. 当前实现差距

- 角色/工作区/授权基础可用；
- 导航与 capability 不是单一来源，存在不可达页面；
- 页面配置/优惠券/自动化 entrance 缺失；
- 员工停用后的令牌失效需验证；
- 审计缺少 before/after/reason 的结构化字段；
- 敏感信息查看审计不完整；
- 无独立 403 页面。

## 12. 非目标与开放问题

非目标：首版不做自定义角色编辑器。

🔵 OQ：总部运营能否跨品牌？
🔵 OQ：审计保留期限和导出权限？
🔵 OQ：是否需要 IP 白名单/二次验证？
🔶 假设：首版能力集固定，后续再开放自定义角色。
