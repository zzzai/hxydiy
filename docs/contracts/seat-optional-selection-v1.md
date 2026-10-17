# SEAT-OPTIONAL-20261017：先提交选单，门店后配位

状态：实现与三端隔离联调完成；待合并、生产发布和门店现场验收。

## 范围

- 门店链接/前台入口允许顾客不选座位，选项目、偏好及加项后提交。
- 每位浏览器使用自己的私有选单凭证，门店入口不合并不同顾客的购物车。
- 座位码仍走原签名入口和共享草稿流程；不自动把无座原单合并到座位码中的其他选单。
- 配位沿用原选单，不假造房位或占用，不改变价格规则、员工权限、物理房态或技师服务状态机。

## 无座选单与匿名主体

- 复用 `POST /api/v1/selection-sessions`：最小输入 `{store_id}`，可选 `source`、`device_label`；响应仍为 `{session, access_token}`。
- 服务端复用座位入口的 `_browser_customer`，创建/复用 `anon_` 用户和既有 `BrowserInstance`，通过 HttpOnly `hxy_browser_token` Cookie 维护匿名主体；Cookie 的 Secure、SameSite、期限和路径与座位入口一致。
- `customer_id` 仅取服务端匿名主体，不接受客户端指定，不强制手机号登录。历史 Cookie 若误绑自然人账号，按既有规则自愈为匿名主体，保留已有实名历史。
- 匿名主体不是会员或自然人身份证明。登录后仍显式调用原 `bind-customer`；退出/切账号不自动解绑服务器历史单，前端应清除旧私有访问上下文，新选购重新建立匿名单，不能沿用已绑定会员的私有 token 报价。
- 之后 GET/PATCH/quote/revisions 使用同一 `session.id` 和 `X-Selection-Token`；单号、短号、门店参数和手机号均不能代替该凭证。刷新恢复原凭证，不重建已有提交单。
- 创建接口没有服务端请求幂等键：创建结果未知可能遗留未提交空草稿，不能宣称创建已去重。提交的 `Idempotency-Key` 复用既有 revision 记录；同键返回已有 revision，目前不比较变更载荷，因此前端同一次提交重试必须保持载荷和键，改选须使用新键。
- 私有草稿 PATCH 不新增共享版本门禁；`expected_version` 仍只用于既有共享座位草稿。报价、发布状态、选项、加项、会员和修订规则继续由现有服务端判定。

## 门店列表与原单配位

`GET /api/v1/admin/v2/selection-sessions` 增加可选 `needs_position_assignment` 布尔筛选及每项字段：

- `position`：无占用记录为 null；有记录时为 `{occupancy_id, room_id, name, status}`，使用该单最新占用记录。
- `needs_position_assignment`：仅 submitted/confirmed、没有任何占用记录且未生成 fulfillment_order 时为 true。它是查询派生信息，不是新增数据库状态。
- 普通员工仍只能看本店已提交的原有只读范围；新字段只描述位置，不增加顾客、偏好、计价或写入权限。
- 管理页增加“待安排座位”筛选、原单号和“安排座位”操作。短号仅帮助对单，复制和详情保留完整 ID。

`POST /api/v1/admin/v2/selection-sessions/{session_id}/assign-position`

- 输入：`{room_id: positive integer}`，拒绝额外字段。响应为既有 occupancy 序列化。
- 沿用现有店长级写权限和选单门店隔离。跨店选单/房位为 404；普通员工/技师无写权限，总部未选择门店不能配位。
- 只接受 submitted/confirmed 原单；从未配位、没有履约订单时才能首次配位。
- 同单同座的有效占用重试返回同一个占用的当前状态，不重复写审计、占用或价格。已有不同位置或已释放历史为 409，不从此入口换位或重开旧单。
- 先锁选单，再按稳定顺序锁目标所属显示房间及床位；复核房位在本店、属于实际服务位、非空间容器、启用且物理状态 available。
- 同座已有活动占用返回 `POSITION_OCCUPIED`；同父房间其他床位已有活动占用返回 `POSITION_OCCUPANCY_CONFLICT`，遵守现有技师按父房间聚合的边界，不新增多人房接待规则。其他扫码入口的既有规则不在本次改写。
- 配位时才创建既有 `PositionOccupancy`，写入原 session、真实 room、两个 active 引用和 `waiting_service`；`actual_start_at` 仍为空，不修改 `Room.status`。
- 已有活动房位/选单唯一约束兜底冲突；占用和两类审计同事务提交，冲突回滚。配位逐字段保持选单项目、偏好、价格快照、金额及确认状态。
- 技师任务自然接收该占用和有效匿名主体，开始/结束服务及 v7 记录仍使用原接口和实际技师归属校验。

## 顾客后续状态

原 `GET /selection-sessions/{id}/service-status` 不扩字段：无座时 `occupancy_status=null`，配位后为 waiting_service；不因此变成服务已开始或可评价。该接口不返回 occupancy 对象或房位号。

- 顾客沿用原 `session_id` 与 `X-Selection-Token` 调用 `GET /stores/{store_id}/service-position-map` 读取实际位置。验证通过后，只向该会话追加本店当前占用的真实服务位，包含床位、不可自选沙发和既有房间；已列出的沙发不重复。
- 公共地图仍只列可自选沙发，其他会话的床位/不可自选沙发不会进入本单响应。仅有 token 不带 session_id 不追加位置；缺失、错误或其他会话 token 不能读取该单位置。

## 数据库与验证边界

- 不新增/修改模型、字段、索引、约束或迁移。复用选单、匿名浏览器、占用和审计表，以及已有 active_room_id/active_session_id 唯一约束。
- hxy 独立工作区基线为 `4aa412787c623e66506cc3e8f88221e1a4a28296`，不是生产目录。
- 合成 PostgreSQL 12 项通过：匿名主体/旧误绑自愈、无座项目加项与偏好、原单配位、跨店/只读拒绝、不可用房位、历史保护、同座竞争、同单重试、同父床位竞争及技师 v7 记录衔接。
- 既有选单、管理选单、占用、扫码共享 85 项通过；仅有既有 TestClient 弃用警告。价格与偏好保持由真实 HTTP 和数据库对象断言覆盖。
- 测试仅使用断外网、限内存/CPU 的合成容器；未连接生产 DB，未使用实际顾客、现网凭据或运行中的 release 测试。合成验证不等于现场验收。
- 三端浏览器闭环完成：顾客原私有单真实响应丢失后以同 session/key/payload 重试且返回同 revision；管理端给原单配位；顾客原上下文读回位置；真实技师角色完成确认、完工、v7 最小记录和同单历史；顾客原上下文读回服务已完成及评价入口。原项目、偏好、衍生项目和 11100 分金额不变。
- 技师实际开始时间未由该浏览器 API 暴露，不将 UI 通过当作该字段运行时证明；配位不提前开始的字段检查及并发边界仍引用对应后端 PostgreSQL 证据。
- 浏览器合成 SQLite 共用连接，最终两预览经共享 FIFO 网关串行访问，仅修复测试设施限制（8 项网关测试通过）；不修改产品认证逻辑，不把 FIFO 浏览器结果当作生产并发证明。先前隔离越界诊断保留，不声称历史生产请求或写入为零。
