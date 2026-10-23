# 荷小悦管理后台 PRD 落地矩阵

日期：2026-10-23
生产 release：`github-f5332e001b30-39886828808`
健康检查：`https://diy.hexiaoyue.com/api/v1/health`
阶段：30 轮持续交付收口基线

## 1. 这份文档回答什么

PRD 套件回答“业务应该怎样”；本矩阵回答“现在到底实现到什么程度、证据在哪里、下一步做什么”。

状态口径：

- **已落地**：有后端接口/数据模型、前端入口、权限与审计、测试与生产部署；
- **部分**：核心路径可用，但仍有明确业务缺口；
- **未落地**：只有 PRD，没有生产代码；
- **不伪造**：没有真实支付、库存、排班能力时，不写成已完成。

## 2. 模块矩阵

| 模块 | PRD | 状态 | 已落地核心能力 | 主要缺口 |
|---|---|---|---|---|
| BR-01 工作台与异常中心 | [workbench-exception](workbench-exception.md) | 已落地（P0） | 今日工作台、异常队列、责任人、SLA 截止、确认/关闭、跨店异常 | 定时自动同步、逾期升级通知 |
| BR-02 选单/订单/结算 | [order-settlement](order-settlement.md) | 部分（P0） | 选单-订单关联、只读结算、对账检查、持久异常、退款登记 | 结算详情/分页、legacy 桌面动作收口、复杂退款对账 |
| BR-03 服务位与房间 | [service-position](service-position.md) | 已落地（P0） | 服务位状态机、占用、释放、异常释放、QR | 清洁耗时口径、跨店服务位视图 |
| BR-04 门店生命周期 | [store-lifecycle](store-lifecycle.md) | 已落地（P0） | 营业状态闸门、开业检查、闭店校验、品牌总览 | 开业清单版本化、预约生效时间 |
| BR-05 目录与页面发布 | [catalog-publication](catalog-publication.md) | 部分（P1） | 项目/加项 CRUD、总部操作门店、页面发布、版本历史、一键回滚 | 商品交易边界、目录 master/门店覆盖、发布审核 |
| BR-06 技师人力 | [technician-workforce](technician-workforce.md) | 已落地（P1） | 账号生命周期、请假审批、冲突检测、自审批禁止、在岗看板、周排班、复制周、总部跨店人力 | 工时统计、班次模板、技师端排班查看 |
| BR-07 顾客运营 | [customer-operations](customer-operations.md) | 部分（P1） | 标签、顾客列表、手机号查看审计、脱敏导出、导出记录、会员权益解释 | 分群执行、顾客合并/去重、导出审批 |
| BR-08 营销与 SCRM | [marketing-scrm](marketing-scrm.md) | 部分（P1） | 券 CRUD、发券、发放/使用统计、SCRM 规则、执行日志 | 券预算、核销明细、批量发券、自动化重试 |
| BR-09 经营分析 | [analytics-metrics](analytics-metrics.md) | 已落地（P1） | 经营事实、数据质量、客单价、上一周期环比、指标口径 | 总部区域/城市/店型、经营趋势图、导出 |
| BR-10 权限与治理 | [governance-permissions](governance-permissions.md) | 部分（P0） | 角色/门店范围、总部未绑定视图、审计日志、写操作审计 | 区域/品牌范围模型、细粒度字段权限 |

## 3. 已落地的跨模块不变量

1. **门店边界**：运营数据按 `store_id` 收敛；总部显式选店或只读跨店视图。
2. **双事实关联**：选单与订单通过 `fulfillment_order_id` 关联；对账差异不静默合并。
3. **异常可追责**：对账差异进入持久队列，有责任人、SLA、确认和关闭审计。
4. **发布可回滚**：页面每次发布生成不可变版本，回滚生成新版本而不是删除历史。
5. **请假不排班**：已批准请假禁止排非休息班；排休息班禁止与已排服务冲突。
6. **敏感数据最小化**：批量导出只给脱敏手机号，完整手机号查看单独审计。
7. **角色不复制**：店长基于技师能力叠加门店权限，不复制第二套端。
8. **指标不伪造**：无口径、无时间范围、无数据来源的指标不上线；数据质量问题显式提示。

## 4. 生产证据

### 4.1 API 与页面

- 管理后台：`https://diy.hexiaoyue.com/admin/`
- 技师/店长移动端：`https://diy.hexiaoyue.com/technician`
- 健康检查：`/api/v1/health` 返回 `status=ok`

已上线并验证的关键路由：

```text
/api/v1/admin/v2/technician-board
/api/v1/admin/v2/technician-shifts
/api/v1/admin/v2/technician-shifts/copy-week
/api/v1/admin/v2/brand/workforce
/api/v1/admin/v2/page-content/versions
/api/v1/admin/v2/customers/export
/api/v1/admin/v2/customer-exports
/api/v1/admin/order-reconciliation
/api/v1/admin/order-reconciliation/sync
/api/v1/admin/exceptions
/api/v1/admin/v2/brand/exceptions
```

### 4.2 数据表

生产数据库已确认存在：

```text
page_content_versions
operational_exceptions
technician_shifts
```

`operational_exceptions` 已包含责任人、SLA、确认时间列。

### 4.3 验证记录

- 后端完整回归：1153 passed，22 skipped，102 subtests passed；关键迁移契约测试通过；
- 前端测试：278 passed；
- 生产构建：通过；
- CI：Trusted PR Gate、Static contracts、Backend tests、Admin tests/build、Manager mobile browser gate；
- 生产部署：通过 workflow_dispatch + 迁移白名单 + 线上健康检查；
- 生产部署曾因磁盘余量不足失败，已清理历史 release 后成功，部署容量检查保留为保护而不是绕过。

## 5. 残余优先级

### P0 收口

- 结算列表详情/分页/退款证据；
- 桌面 legacy 订单动作接口收口或异常授权门；
- 异常定时同步、逾期升级通知；
- 总部品牌/区域/门店范围模型。

### P1 深化

- 页面预约发布、审核、生效时间；
- 顾客导出审批与文件有效期；
- 券预算、核销明细、批量发券；
- 经营区域/城市/店型维度与导出；
- 技师工时、班次模板、技师端排班；
- 顾客分群执行、合并/去重。

### P2 体验

- 表格密度、空态、错误恢复、键盘可达性；
- 移动端弱网和深链降级；
- 指标趋势图和异常根因提示。

## 6. 结论

PRD 套件覆盖 10 个业务模块，已形成可评审的角色、门店范围、状态机、流程、异常、权限、审计、指标和验收标准；对应 P0/P1 的核心链路已经进入生产并有测试和审计证据。

仍有明确未完成项，因此不能把“全部业务能力已实现”当作事实。下一阶段应继续按本矩阵的 P0/P1 残余项推进，而不是新增表面页面。
