# 移动服务待办收尾契约

## 范围

基线：`5329b35a771aa33669bce934e7b3264964c3e522`（PR #377）。店长与技师共用 `/technician` 移动体系，角色权限不变；不新增数据库迁移、支付、退款、资金对账、营销、外部消息或生产测试数据。

## 记录完成口径

- 记录是否已填写与顾客是否确认是两个独立维度。本人有效 v2–v7 记录（taxonomy 对应且未被更正替代）即算已填写；`no_additional_notes` 也是有效完成，不要求编造内容。
- 补填只能针对本人结束服务的现有审计所证明的占用；取同一选单最新占用，与现有记录写入 API 一致。匿名无顾客归属、缺少本人结束审计、已换到新的未完成占用均不提供补填任务，不猜测旧记录归属。
- 店长 `GET /admin/v2/manager/workbench` 增加 `record_follow_up`：`window_days=30`、`pending_count`、`technicians[{technician_id,name,count}]`。仅本店、当前在职且可操作的技师、近30天真实结束的服务；不含未来时间和未结束服务。
- 店长只看到谁有多少条待填，不加载或返回顾客标识、身体信息、私人记录正文，也不代替技师写记录。提示技师从“历史服务→只看待填写”进入。
- 技师 `GET /technician/service-history` 增加 `record_status=all|pending|completed`，默认 all 保留旧客户端行为，非法值422。既有 `profile_status` 继续表示顾客确认维度。历史筛选没有30天截断，支持本人补填更早的可操作服务。
- 可补填项新增 `record_task`（选单ID、本人该次服务的顾客ID、项目名称、服务位名称）；不可补填时为 null。复用现有 v7 保存 API、作者权限、门店隔离与幂等键，不新增写接口。
- 写成功后技师重新读取当前筛选，店长下次刷新读取最新计数；失败保留编辑器和任务。不会因打开页面或刷新写入记录。

## 异常知悉与处理

- `GET /admin/exceptions?status=unresolved` 返回本店 open 与 acknowledged，resolved 不在待办；原默认 open 不变，既有返回上限200保留。
- `POST /admin/exceptions/{id}/acknowledge` 锁定本店目标行；首次知悉保留原处理人、时间及审计行为，再次知悉返回原结果，不覆盖原时间/处理人、不新增审计；resolved 409、跨店404。
- 移动端不回显内部 title/detail/type 编码，只用受控业务标签。已知悉项保留并显示“已知悉·待处理”，不能当成已解决；入口到本店服务单供核对，实际解决仍用现有异常中心，不伪造自动修正。
- 工作台 `open_exceptions` 现为未解决总数（兼容键名），包含已知悉项；`overdue_exceptions` 为其中逾期子集。`attention` 不重复叠加逾期子集。
- 页面初次进入及恢复可见/pageshow 时做只读刷新；重复请求以最后一次有效请求为准，身份变化/卸载后的响应不得回填旧任务。知悉按钮有同步重入保护；请求失败不显示“没有待处理”。

## 自动检测尚未开启的原因

旧 `_order_reconciliation_result` 以 confirmed/in_service/completed 选单缺 `fulfillment_order_id` 判为缺订单。但当前链路允许无座提交，并用 PositionOccupancy 履约，不保证存在旧支付 Order。因此不能把旧 sync 接到打开页面/定时器上，否则会制造误报并写入真实异常队列。

本批的“自动刷新”仅表示重新读取既有异常和实时计算记录待办，**不等于漏单异常自动生成**。后续必须基于现行选单/占用状态机定义可证明的履约断链，再用合成数据验证合法无座、未分配、已完成与冲突场景；不恢复款项对账，不自动修复旧数据。

## 验收证据

- `tests/test_mobile_workbench_closeout.py`：记录待办与顾客确认分离、保存及同键重试消项、匿名/替代占用排除、跨店及角色隔离、知悉重试及逾期不重复计数。
- `admin-react/tests/manager-tasks.test.ts`：未解决状态投影、内部字段不泄露、畸形响应不冒充空列表。
- `admin-react/tests/mobile-closeout.browser.cjs`：真实 React 组件的知悉重入/失败重试、返回刷新、加载失败、身份变化迟到响应、补填保存和失败保留。只接合成适配器，禁止所有真实 API 网络请求；合成 pageshow 不冒充真实 BFCache 命中。
- 既有服务历史、v7记录、管理选单合同回归；前端全量测试/构建以及 CI。
- 发布与现场结果另记：CI/合成浏览器/健康检查不能替代真实企微、弱网或人工门店验收。
