# 企业微信门店员工接入 v2 增量

状态：2026-10-18 已通过 #280 合并并发布 `bfa16198b34666e28ff8ed2d5d7924000b909664`，已批准三人精确批次创建/绑定及重放保护完成。原 GitHub Deploy 容量失败与同包原发布器的受控服务器恢复成功分别保留，完整证据见 `../CURRENT-STATE.md`、`../WORK-STATUS.md`。三人本人真实登录、手机/BFCache与真实报告来源未验，不用合成测试代替现场验收。

## 范围与角色

仅支持明确本店的在职技师与店长；不支持总部、普通员工、未知角色或多工作区。企微 canonical UserID 必须经同一应用官方接口确认，登录不能按姓名或手机号猜绑定。正式建号输入只在仓库外的受限私有文件，个人数据不写本契约。

- 技师：原 `Staff.role=technician`、同店 Technician、available/busy 和身份版本规则保持。
- 店长：数据库 `Staff.role=manager`；`store_id` 指向同一真实门店，必须恰好一条 active `StaffScopeAssignment`，且 role=`store_manager`、scope_type=`store`、scope_id=绑定门店。
- 2026-10-21 增量：店长可绑定同店有效 Technician，`Staff.technician_id` 与企微身份 `technician_id` 必须一致且都为 null 或同一个有效技师；店长因此同时拥有技师任务能力和门店管理授权。旧的无技师档案店长保持兼容，但产品迁移要求所有店长补齐技师档案。
- 缺授权、多授权、总部授权、其他门店、普通员工或角色错配均拒绝，不挑选第一项，也不借 legacy token 默选。

## OAuth 响应与每次请求

沿用 v1 authorize/callback/exchange、一次性浏览器绑定、epoch、防重放及300秒官方证明。技师响应不变。

店长 exchange 返回：

```json
{
  "token": "<server-signed scoped token>",
  "auth_method": "wecom",
  "staff": {"id": 1, "name": "<name>", "role": "store_manager", "store_id": 1, "technician_id": null, "store_name": "<store>"},
  "selector_token": null,
  "workspaces": [{"assignment_id": 1, "role": "store_manager", "scope_type": "store", "scope_id": 1, "scope_name": "<store>"}]
}
```

示例编号为说明而非真实身份。JWT 使用既有 `token_type=staff_scope`、真实 `role=store_manager`、精确 assignment_id/scope_type/scope_id，同时保留 WeCom external_identity_id/binding_version/credentials_version。每次请求重验 Staff、身份和唯一授权；授权撤销、角色/门店改变、JWT scope 不符立即拒绝，不受官方证明缓存窗口影响。

前端严格校验 staff 正整数 id/store_id、technician_id=null、selector_token=null 和唯一同店 grant，再复用现有导航别名 manager。2026-10-20 移动工作台增量将店长默认落地改为 `/technician/store`（已于2026-10-21随 PR #299 发布；生产与现场验收边界见 `../CURRENT-STATE.md`）；技师仍进 `/technician/today`。回调按本次验证身份决定落地，不能读取另一角色的保留会话。总部、任意 return URL 和多工作区选择均不在本批范围。

### 店长手机工作台增量（2026-10-20设计，2026-10-21已发布）

- `/technician/store` 及 `/technician/store/login` 固定使用既有 admin slot；登出/401 不回退到保留的 technician slot，不清除另一角色会话。店长必须 manager、正整数 store_id、technician_id=null。
- 同一移动壳内为“门店工作台”，提供“选单 / 座位”两种视图；选单按待确认/待配位/已确认/全部筛选；调用既有 `GET /admin/v2/selection-sessions` 的 page/page_size，使用服务端 total。待配位仅传 needs_position_assignment=true，不附加 submitted 过滤。
- 项目、状态、服务位优先展示；金额只用 pricing_snapshot 的 payable_total_cents/applied_price_type，合法零价保留，缺价显示“金额待核实”，不按会员身份重算。来源枚举仅中文展示，存储值不改。
- 确认/取消/配位与加选批准/拒绝沿用既有管理接口和权限。加选动作传 change.id，拒绝原因非空；操作成功后重新拉取列表与加选，不用缺少 position 的动作响应覆盖完整选单。错误保留目标和输入，403禁用操作，401/身份epoch改变清除旧界面；不新增接口、权限或幂等参数。
- 不挂载技师业务页面，不请求技师 me/tasks/履约、顾客画像/报告/标签。空列表保持紧凑；没有加选时不显示加选空卡。
- “更多 → 电脑后台”是主动选择，不再自动跳后台。普通企微离页清当前角色会话并隐藏旧界面；仅显式电脑后台交接保留店长会话，返回缓存页面先隐藏旧数据再重新验证。合成生命周期测试不等于真机/BFCache验收。
- 验收仅合成数据，禁止对生产调用 live-service-position-map（该GET可能清理过期占位）。后端、数据库和真实订单不在本增量范围。

### 座位只读视图增量（2026-10-21，PR #299 已发布）

- 全店服务位仅来自既有 `GET /admin/live-service-position-map` 的 positions，不从20条分页选单拼接、不调用固定布局补位、不虚构服务位。实际 sofa/bed/room 分别展示为沙发/床位/房间；停用服务位单独可收起，仍有关联或异常时默认展开。
- map.store_id 必须等于当前店长 store_id；展示关联项目前必须同时满足 occupancy.store_id=map.store_id、occupancy.room_id=occupancy.active_room_id=position.id、occupancy.selection_session_id=occupancy.active_session_id=selection.id，且 ID、状态、项目结构有效。旧类型仅兼容新增可选 active_session_id，新视图缺值即待核实，禁止回退替代。关联不一致不展示任何该选单项目/价格；整个 map 错店或加载失败显示错误与重试，不降级为空位。后端会话门店完整性沿用受控写入及活动关联唯一性，本视图不声称 map 单独重验 session.store_id。
- occupancy 状态为准：held=选购中、waiting_service=待服务、in_service=服务中、post_service_present=已结束服务·待离位确认、cleaning=已结束服务·清洁中。selection.confirmed 只是选单已确认，不能推断服务未结束。双空关联为“暂无当前选单”，不等同现场空闲。
- 座位详情只读展示真实项目/偏好、选单 ID/状态、来源与价格快照（零元有效，缺价待核实）。不推断顾客、手机号、技师，不补查历史分页或用 live-board/rooms.current_tech 拼接。确认/取消/配位仅保留在选单视图，不新增开房、离位、开始或结束服务按钮。
- 详情绑定 position.id + occupancy.id + selection.id；刷新遇到关联改变时隐藏原内容并显示“关联已变化”，必须关闭再打开，不能静默切换新单。地图请求受会话 epoch、门店、组件存活、页面可见生命周期及请求版本约束；晚到的旧读、换店、退出或 pagehide 均不得回填旧地图。选单写入成功失效地图版本，切换回座位重新读取完整地图。
- 合成验收覆盖375/390宽度、25个真实返回服务位、空/停用/异常关联、服务结束、零价/缺价、错误不当空位、换单守卫、迟到响应、换店、退出、真实浏览器 pagehide 与写后重载。生产写入仍为0；合成浏览器行为不等同真实手机企业微信/BFCache验收。

原技师任务/报告/标签接口仍只接受技师且维持本人当前在店服务范围；店长只获得其既有门店管理权限，不借此取得技师顾客档案新权限。

## 数据与运维

### 2026-10-20 技师官方姓名与本地姓名分离

- 正式工具仅对技师接受可选 `expected_wecom_name`（1–32 字符、无首尾空白或控制字符、非空字符串）。显式值交给原 `WecomProvider.verify_member` 严格核对官方姓名；`name` 仍是已经用户确认的本地员工/技师姓名。不得猜映射、修改官方响应、跳过主体或在职/同应用可见性校验；店长输入此字段仍拒绝。
- 不提供该字段时，继续用 `name` 校验官方姓名，规范化请求不增加任何默认键，旧请求摘要、旧审批及整批审计重放保持兼容。显式字段与 canonical UserID、本地姓名一起进入请求摘要，并通过该摘要绑定预览和审计；改变官方姓名字段必须重新预览，不能复用旧审计。普通输出仍仅含 label/编号/摘要，不输出姓名、手机号或企微主体。
- 用户提供的原始编号应原样提交同一应用的官方 `user/get` 取得其返回的正式 UserID，再做 canonical 化和主体/官方姓名复核；不得先小写一个尚未解析的原始编号，也不得按本地姓名或手机号猜正式 UserID。
- 每批最多三人、门店锁、整批事务、冲突拒绝、旧行保护和重放零新增规则不变；新旧员工不得混用旧批次审批。只从经审查的精确脚本版本运行此运维工具，可复用一致的现网依赖，但不覆盖生产安装目录、不改 API/登录流程或 schema，不为接入重发整站。每个新批次仍须私有名单、预览、备份及真实隔离恢复、审批摘要、事务和前后核验。

新增迁移仅放宽外部身份 technician_id 的非空约束，保留 FK、唯一约束和所有旧绑定。降级若存在空技师编号身份必须拒绝，不能通过删除绑定满足非空约束；应用回滚保留数据。

正式员工批次工具与 `create_test` 分开：默认预览、明确每人的 canonical subject/门店/真实角色/账号资料、精确预览摘要确认、锁后重查、同名或手机号/账号/企微主体冲突拒绝、整批事务、审计、重放零新增。店长只建 Staff、唯一门店授权与绑定；技师只建 Staff/Technician/绑定；随机密码只在内存生成并哈希，不发送明文或短信，不修改旧账号和授权。

2026-10-18 首批仅用户明确批准的三人；后续独立名单必须有单独授权和新的私有请求，不重放旧批或修改其他员工、顾客、订单、余额、会员资料。复用服务器 Secret，真实备份恢复/定向回归/必需 CI 后才应用，不把脚本预览视为完成。

正式工具：`python -m scripts.provision_wecom_staff --input /private/batch.json`。应用追加 `--apply --expect-preview-sha256 <完整摘要>`。顶层为 `corp_id/store_id/members`；最多三名成员，每人明确 `label/userid/username/name/role`，label 仅用 `manager_1` 或 `technician_1` 等非个人编号；技师另需 `phone/code`，店长禁止技师字段。仅复用本工具同一完整请求审计确认的整批结果；部分已存在、旧身份停用、角色改变或资料冲突均拒绝，不自动修复旧人。手机号来自已批准私有清单；官方未返回手机号时不宣称已官方核验手机号。

既有单人绑定 CLI 支持明确 `technician_id:null` 的合法单店店长，仍需完整 Staff/门店指定和唯一授权；不经 `create_test` 路径创建正式员工。随机密码不可知，仅哈希保存；后续任何重设须走原有受控流程。

### 2026-10-27 店长默认入口修复

- 店长企微登录成功后统一默认进入 `/technician/store`，不因同时保留技师档案而进入 `/technician/today`。既有评价待办深链继续进入门店工作台。
- 兼有技师档案的店长仍可主动切换本人今日服务、服务记录、我的；普通技师默认今日服务。只修默认落点，不改角色、会话槽隔离、接口权限、门店范围或绑定。
- 无技师档案店长仍不得加载技师业务接口；合成 OAuth 回调、手动切换和电脑后台交接分别验收，真实企微终端由人工确认。
