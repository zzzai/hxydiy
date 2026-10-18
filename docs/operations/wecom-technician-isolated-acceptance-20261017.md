# 企微技师接入：隔离验收记录

## 2026-10-18 专用测试技师补充授权

已最小只读核实无明确可复用的测试技师；用户允许新增“企微测试-张震（勿派单）”账号及档案，并已知晓它会出现在门店技师列表。精确允许新增 1 Staff（technician）、1 Technician、1 外部身份绑定；不修改原管理员或现有测试员工，不发送短信，不输出或保存明文密码。受控操作先预览、核实目标门店/规范企微身份及唯一冲突，再事务提交与幂等复核；旧业务行保持不变。本轮只验证登录、身份/门店与空服务列表，不创建或分派真实顾客服务单。此条解决下方新增 Staff/Technician 的授权缺口，实际执行结果仍待回执。

## 2026-10-18 正式发布授权更新

用户已明确授权：真实备份并验证可恢复后新增 `staff_external_identities`、`staff_oauth_attempts`、`customer_tag_contributions`，仅绑定确认的测试身份；必要验证和 CI 后合并发布本批至 `diy.hexiaoyue.com`。沿用服务器现有 Secret，不修改旧订单、顾客资料、余额，不删除旧数据，不自动降级三表。后台为唯一生产操作窗口，总控审阅最终差异和证据；技师端验证正式入口。此授权覆盖下文旧阶段“待授权/不合并/不部署/不动生产库”，但不代表迁移、绑定、发布或现场验收已经完成。

张震被用户确认是管理员，暂按测试技师身份使用。必须保留原管理员角色，不能绑定到真实技师、用管理员会话绕过技师检查或使用真实顾客订单测试。后台先仅查询目标门店必要 Staff/Technician 标识、角色及状态，核实能否复用独立测试身份；如需新增 Staff/Technician 行，先报告精确影响，不默认纳入三张新表授权。规范企微身份采用官方验证返回值，不按姓名或未核验输入自动绑定。

沿用既有有效隔离证据，只验证新修正和必需 CI。发布回退优先关闭企微功能或回退应用并保留三表；不得自动 DROP 新数据。首次桌面验收仅登录、身份/门店及本人服务列表，空列表是有效结果，不为了测试创建或分配真实服务单；真实手机、BFCache 和未接入的报告来源保持后置/未验证。

## 2026-10-18 最新决定：标准正式域名接入

用户要求直接复用 `diy.hexiaoyue.com` 并优先完成企微对接。停止原同源测试适配或独立域名配置路线，既有测试静态页不扩建、不自动删除；真实 BFCache 专项和手机验收后置，不阻塞首次桌面接入。原候选前端无需重做，正常部署的固定 `/technician` 与 `/api/v1` 已符合目标；观察工具不属于产品，不随发布上线。

后台确认显式个人可见限制是业务 provider/合同/测试而非单纯工具前置，正在既有独立树实施部门可见的最小修正，保留官方身份/应用范围、在职、DIY明确绑定、角色/门店、state/Cookie/一次性交换及撤回检查。其他必要差额为 compose 的既有 WECOM 配置注入、仅本次迁移文件的发布白名单，以及可预览/幂等/冲突拒绝的明确账号绑定。不绕过迁移检查，不把 Secret 写入 Git，不重跑旧通过项。

三张新增表为 `staff_external_identities`、`staff_oauth_attempts`、`customer_tag_contributions`；现有迁移无旧业务表 ALTER/UPDATE/backfill，但 downgrade 会删除新表记录，不能自动执行。总控已集中请求生产备份/可恢复验证后三表与指定账号绑定、必要 CI 后合并发布授权，并请求确认张震应绑定的现有 DIY 技师账号；管理人员不能猜成技师。答复前不访问生产库、不正式绑定、不合并或发布。本节取代后文仍要求测试域名与显式个人配置的待办；既有验收事实保留。

## 2026-10-18 电脑企微验收准备更新

15:22 进展：独立 HTTPS 验证页 `/__wecom-test/ready` 返回 `https-ready-login-closed`，业务入口/API 仍 403、API/PG 未启动。受控网关精确追加、备份、nginx -t 和平滑重载完成；最新配置 SHA256 `7c9b5f5446b35d7309485f51484fe74b6e9323fddfaa7a53259546328f4ce907`，非测试配置前缀未变。已挂载用户提供且由总控核验的精确 WW 文件，SHA256 `b2d633a8b2d7794cd3dd8833be930ea0b64d61f988dd29e351a8dbc2e3c61a23`，未改生产验证文件。回执位于 `output/wecom-real-device-entry-20261018-v1/`，总控已读配置/生效回执，不重复后台通过项。

已一次向用户提供测试主页（含单独 PC 主页若有）、OAuth 可信域名、明确成员三项配置；完成后再开受限桌面窗口。当前只完成静态入口和工具准备，不宣称真实登录、资料或 BFCache 验收通过。以下为本阶段早先核验，HTTPS 准备状态由本段更新覆盖。

用户允许临时独立测试域名与指定测试成员，并在确认 DNS/可见范围配置后要求先电脑端可用。安卓真机/手机版本及移动缓存恢复后置，不再作为桌面启动前置。仍保留已有修改，不提交、不合并、不部署业务版本、不连接生产库。

后台 15:12 新鲜核验 `wecom-test.hexiaoyue.com` 的 A 记录仅为 hxy IP、AAAA 为空；官方应用启用、成员查询成功且在用、返回姓名与用户工作台截图一致，明确成员列表仍为空。工作台可见可能由部门范围提供，不能宣称应用不可见或用户 ID 无效。当前未创建身份绑定、未放行登录；主页仍空，可信回调仍未设为测试域名。独立 HTTPS 默认拒绝静态页正在准备，不等于业务入口就绪。

技师工具已冻结在 `tools/acceptance/wecom-real-device-v1/` 共六文件，仅部署观察器和两个中转页静态文件到测试 origin，不随产品发布。远端 Node 两项语法检查及 9 项工具回归通过；总控读取源码/测试/README/最终回执并核对哈希，不重跑。远端 `output/REAL-DEVICE-TOOLS-v1-checks.txt` SHA256 `2ac37b1715a2f93241bb4645fe39fb4a7fecb761ff793f97c87acb701af32452`，`output/REAL-DEVICE-TOOL-DELIVERY-20261018-v1.md` SHA256 `0df47cfd051cc57d8bd257e060ef9256180f523ba5caf07959031624b5cd4da9`。真实事件只输出白名单枚举/布尔/相对时间，缓存观察不等于安全通过；缺失、不命中仍未验。

桌面握手须一次给齐：HTTPS 实际可达、PC 实际入口/可信回调、明确测试成员到隔离技师绑定、指定合成服务/资料、观察工具接入、资源限制与截止/关闭责任。仅在条件齐备后，由总控用当前本机企微执行一次本人合成资料只读及同 WebView 完整文档后退，技师窗口判读；不重做结束服务、保存记录或 R5/R6 已通过项。普通重载安全回账号登录页不称自动登录恢复，桌面结果不延伸成手机验收。电脑当前文件版本为企微 5.0.9.6009、Windows 11 build 26200，仅环境信息，不是功能通过证据。


日期：2026-10-18 13:56（Asia/Shanghai）。状态：PostgreSQL 合同与完整构建、原隔离 API r4 前七组证据沿用，不重跑。R5 代理最小修复后，原前置下三次 OAuth 按原 9 秒标准及身份语义通过，第三登录超时已关闭。R6 一次真实后退的普通重载安全登录通过，真实 BFCache 未命中，保留 partial/未验证，不宣布全量闭环完成。R5/R6 后台保护、认证范围与资源关闭通过。没有生产库访问、提交、合并或部署；旧失败记录保留。

## 授权与基线

- 用户允许后台、技师窗口按三表方案仅隔离实施和联调，总控跟进验收。保留已有修改，不动生产库、不提交、不合并、不部署。
- 工作区：`hxy:/root/hxy-diy-development/wecom-technician-20261017`；分支：`codex/wecom-technician-isolated-20261017`。
- 基线：`77ce71fd0133471a067b9fdeefa59c3c93eaad6a`，已通过 GitHub 官方 REST 核验为当时 main；创建时工作区干净。原 seat-optional 工作区及其两个未跟踪构建记录文件未变。
- 方案：既有 backend-preflight-v2 与总控补充；不重复设计。生产域名归属验证已单独完成，但不证明企微登录有效。

## 唯一文件责任

| 负责人 | 写入范围 |
| --- | --- |
| 管理后台+后端 | hxy-server；共享 admin-react/src/api.ts、auth.ts 与必要通用入口；业务 contracts、TEAM-MEMORY、admin workstream；隔离 PG/API 与后端测试 |
| 技师端 | admin-react/src/technician/、专属 React/浏览器测试及 technician workstream；共享签名通过后台协作，不改共享文件 |
| 总控 | CONTROL-BOARD 与本记录；交付范围、冲突协调、只读复审、证据验收；不重复写业务实现 |

## 已冻结边界

- 新表仅 StaffExternalIdentity、StaffOAuthAttempt、CustomerTagContribution；不改旧表唯一约束，不回填/去重旧业务，不引入 Redis 或预服务 grant。
- 每次明确从企微工作台进入先重验当次身份；旧 DIY token 不能先显示或请求上一账号业务。站内导航不循环 OAuth。
- OAuth attempt 和成员证明的新配置初值均为 5 分钟，成员证明过期重验失败拒绝；这不是现网配置修改。解绑仅撤销对应企微绑定会话，保留原密码会话规则。
- 保留原待接服务入口，与本人服务单分开；不为看档案提前 confirm。匿名/未绑定顾客仍可履约，不假造历史身份。
- 本人服务中或结束仍在位且可靠客户关联成立时读取获准档案；离店、释放、清洁或关系失效后拒绝并清理前端缓存。本人历史记录原权限不变。
- 仅店长批准的本店 active/manual 普通标签；无自由造词、v7 私密转标签、外部企微标签同步。技师只撤回本人贡献，其他来源仍保留。
- 保留店长原有同店旧标签关系合法维护；旧关系与新贡献集合去重，列表、筛选、计数一致。不把旧来源一刀切改为只读。
- 报告正负分支使用显式合成用途证据；真实来源证据缺口不得伪造或默认放开。不增加面部原图权限，不增加顾客 H5 重复授权。
- 合成 OAuth provider 只可测试依赖注入，不得成为生产可调用假登录。普通隔离测试不读取或挂载真实 Secret，不使用真实员工/顾客或生产备份。

## 总控已核验的恢复与阶段证据

- 恢复检查未发现本批遗留运行进程，无需删除或终止其他任务。历史失联根因未确认；无 OOM 日志不等于排除资源影响。
- 本批测试容器已落实 CPU、内存、无 swap、PID 与超时限制；新 PG tmpfs 为 128 MiB。具体值、资源阈值及串行运行顺序见 `wecom-technician-resource-resume-20261017.md`。生产容器、数据库与现网配置未改。
- 后台 r1 配置解析失败和 r2 迁移字段长度不一致均留原始证据，不抹去失败；r2 发现的 `selection_session_id` 长度差异由两文件 v4 增量修正并补回归，不改旧表。
- r3 的 `pg-validation-result.json` 与 JUnit 均为 67 passed、0 skipped、0 failures、0 errors；三项真实 PostgreSQL 并发用例全部执行。实际新增三表、downgrade/reupgrade、模型结构与 56 张旧表保护通过。
- 数据库基线使用合成模型 scaffold 后 stamp，再实际执行会员卡迁移和本次增量迁移；未验证历史空库从零完整迁移链，不将两者混称。
- r3 guard 为 `passed_stopped`，两个本批容器确认 exited。总控复核日志最低 MemAvailable 2253 MiB、根盘空闲 3632 MiB、PSI full avg10 最大 0；该轮 cgroup OOM 计数为 0。资源充足仅证明本轮受限测试，不推断历史故障原因。
- 后台 v3 的 28 文件快照/补丁/路径集已核；远端 LF 规范化以后以 installed-lf-manifest 为准，另叠加 v4 两文件增量。技师 v1 的 14 文件及摘要重试 v2 两文件增量已核。总控未重复写业务实现。
- 独立后台审查的问题已修正；技师只读审查未发现 Critical/Important，摘要失败重试关闭面板的 Minor 已用两项 RED/GREEN 与定向复审关闭。
- 技师已有 11 组真实 React/合成 HTTP 验证及新增 2 项摘要重试通过；不是完整 App 接真实 API 证明，也不是企微手机登录或真实 BFCache 证明。
- r3 证据：`output/wecom-technician-resume/20261017-r3/`（资源与增量回执）、`hxy-server/output/wecom-technician-resume/20261017-r3/`（迁移与合同测试）。本机脱敏副本在后台工作区 `output/wecom-technician-20261017/resume/evidence-r3/`。
- 完整前端构建 r2 在 70.13 秒触发 PSI full avg10 连续三次阈值，guard 已停该 unit；只完成 4060 模块转换，没有完整 bundle。最低可用内存 1829.7 MiB，磁盘 3629.2 MiB。不得将部分产物用于验收或推断此次压力就是此前失联原因。脱敏证据在技师工作区 `output/wecom-technician-20261017/build-evidence-r2/`。
- 用户随后明确允许仅将完整前端构建移到本机：使用与 hxy 精确核验的源码快照和固定依赖、资源上限，不在本机改业务代码。服务器不重复重型构建，API/PG 仍在 hxy 的隔离环境，合并/部署/生产库边界不变。
- 合成 fixture/guard 独立只读审查未发现阻断接线问题。浏览器的 HTTPS/SSH 回环、SPKI 证书限定与点击前外联拒绝仍须实际证明；API 最长 480 秒，仅在完整客户端准备好后启动，不占用窗口等待编写测试。
- 本机完整构建现已通过：159 文件的 hxy 精确快照、349 项固定依赖版本核验；Windows Job Object 2 GiB、Node heap 1536 MiB、600 秒上限，实际 130.55 秒 exit 0，峰值 978423808 字节，43 产物，159 源文件哈希未变。该阶段仅本机构建，没有改业务源码或生产。回执在技师工作区 `output/wecom-technician-20261017/full-app-local-build-v1/`。
- 完整 App 的 HTTPS 静态加载与登录/激活导航通过（API 转发关闭、请求 0）。TLS 六组、独立 HTTP transport 无 CA 拒绝/指定子进程 CA 成功、固定错误码脱敏回归与定向复审通过；未放宽系统信任或全局忽略 TLS。
- API r1 客户端异常提前退出，缺正常业务 final report，不能记为联调通过。后台已正常 stop_request 并确认 public_unchanged；guard 为 window_closed_stopped，两个本批容器退出，原 PG 未启，精确 relay PID 已停止且 18000 无监听。
- r1 最终只读计数：612/613/614 仍 waiting 且无技师，服务动作审计/状态转移/v7 均为 0；801 两作者贡献各 active 1，802 无新增。OAuth attempt/session 未统计，不能把服务/标签无写扩展为全部数据库无写。r1 证据原样保留在后台工作区 `output/wecom-technician-20261017/resume/fixture-e2e-r1/`；修复驱动、冻结新版本并完成离线失败回收自检后，才协调新窗口，不盲目重放业务。

## 必需验收

### API r2/r3 的实际终态

- r2 客户端停在 provider 导航同步等待，尚未通过业务检查组。r3 修正该驱动后，实际隔离 authorize/callback/exchange 各两次完成，本人和另一测试账号往返、无关资料拒绝、本人摘要/历史/评价/报告读取已走到；随后显式业务检查组完成前卡在 closeDrawer 的 Escape 后隐藏等待。两轮均不计为八组业务通过。
- r3 后台正常 stop_request/public_unchanged=true；guard window_closed_stopped，PG/test/旧PG均已确认停止；relay与controller退出，18000及客户端18443无监听。最终合成业务计数无新增：612/613/614仍waiting且未认领，服务审计/转移/v7为0，801旧贡献保留、802无新增。这不包括OAuth状态，不能称整库零写。
- r3 后台证据 `admin/output/wecom-technician-20261017/resume/fixture-e2e-r3/`；客户端 `technician/output/playwright/wecom-real-api-1792252672339/result.json`，完整结果各在 BACKEND-R3-CLOSED-v1.md 与 CLIENT-R3-RESULT-v1.md。
- v5 两处驱动修正（显式Close及匿名状态按钮）已有离线RED/GREEN和后续选择器/payload核验，交付为 CLIENT-DRIVER-v5-HANDOFF.md。当时为 frozen_not_armable；之后在独立安全修复验收后，以 v6 驱动绑定新 r4 运行身份接续。r3 未重用，两棵树的未提交源码未混合。

### API r4 的实际结果与剩余诊断

- r4 的七组实际 API/隔离 PostgreSQL 流程通过：身份和档案读取；标签提交丢响应后的同键重试/本人撤回；612 开始/结束/v7 保存和历史读回；614 匿名履约及越权负例；门店释放后清除档案；跨标签页换账号清除未保存内容；613 在途旧提交响应不得污染新账号且仅一次 POST。
- 最终数据库交叉核对：确认/结束/相应审计各3；612已释放、613仍在位、614匿名；612和613各1份v7、614无v7。旧标签同事贡献保留，本人撤回和新标签幂等结果符合预期。公共schema保护通过。该轮从合成待服务单起步，不替代顾客新建无座选单和门店配位的独立端到端证据。
- 第八组在第三次 OAuth callback 的 page.goto 等待 DOMContentLoaded 9000ms 失败，尚未进入 neutral/goBack/BFCache。三次 callback303、两次 exchange200 是响应计数，不能据此断言第三次 exchange 没有发出。整轮结果仍 failed，不标为八组通过或真实企微通过。
- r4 两个本批容器与旧PG均已停止，无OOM；API/guard分别49.02/62.40秒，最低可用内存2208.66MiB、磁盘3458.93MiB、PSI0。controller、relay、客户端入口PID已退出，18000/18443无监听。浏览器/代理/终端完成await关闭，未记录浏览器OS PID，因此不扩展为全部浏览器进程为0。
- 证据：technician/output/playwright/wecom-real-api-1792265868035/result.json；CLIENT-R4-RESULT-AND-DIAGNOSIS-v1.md；admin/output/wecom-technician-20261017/resume/fixture-e2e-r4/closed-result.json（SHA256 e88d8f64fb30e0318f8ea9a77697a309c69da35915783f3788e0e0bfe1950767）。
- 下一轮 fixture-auth-diag-r1 仅诊断认证/导航：后台manifest 548685481c3c4b713bd6dc0211298127ee1af8316fef2b7a0774b6a50ca1e8b7；客户端manifest 2e773fe0659ab0cc7abf48356608c6350a3ce5ad58bf5d708a0e47b5eb476301。独立复核无阻断后总控已单次放行，执行结果待收。保留DCL9秒标准，只有六条API及精确OPTIONS，业务摘要除窄认证豁免外必须不变。不重跑前七组业务写入；纯认证诊断未复现脏草稿/在途v7前置条件，成功也不能关闭原第八组。

| 检查 | 责任 | 状态 |
| --- | --- | --- |
| 合成旧 head 上实际三表增量迁移；旧数据与 schema 保护、约束和并发验证 | 后台 | r3 通过；历史空库全链未验，见上方基线限制 |
| state/code/exchange 重放、并发一次性、浏览器绑定、固定跳转及日志无凭据 | 后台 | 合成 provider 合同与真实 PG 并发通过；真实企微未验 |
| T1 有效旧 token、T2 工作台进入、迟到 200/401/callback、BFCache 与退出清理 | 两端 | 合成 HTTP 的真实 React 时序通过；r4跨页换号/迟到提交响应隔离通过；第三次OAuth导航失败，实际BFCache与真实企微未验 |
| 未绑定/停用/跨店/他人单拒绝，原密码登录兼容与企微解绑隔离 | 后台 | 后台合同通过；r4浏览器/API中的本人/跨账号及匿名负例通过；不扩大为所有设备/解绑现场验证 |
| 无座提交、门店配位、技师开始/结束、v7 记录保存与本人历史闭环回归 | 两端 | 既有无座合同证据保留；r4从合成待服务单开始的履约/v7/history通过，本轮未重新执行顾客新建及门店配位全过程 |
| 可靠关联档案、获准历史/评价/报告；离店/释放收权及匿名履约不受阻 | 两端 | 后台合同与r4真实隔离API闭环通过；报告为合成来源，真实报告来源仍拒绝 |
| 标签来源叠加/撤回、同键重试/冲突/并发，店长原维护及管理筛选计数 | 两端 | 合同及PG并发通过；r4浏览器丢响应重试/撤回/同事贡献保留通过；管理端维护仍引用合同证据 |
| React 类型检查、构建及真实浏览器使用隔离应用 API/PG | 两端 | 本机类型检查、受限完整构建通过，哈希冻结产物未重建；r4前七组通过，第八组未关闭；缩小认证诊断partial已结束，不冒充原场景通过 |
| 独立只读复审与精确文件/证据核验 | 总控 | 后台/技师源码、r4驱动和诊断冻结包复审通过；r4数据库与资源证据已核，剩余诊断结果待收 |
| 真实企微测试成员登录、手机切账号 | 人工配合 | 尚未具备测试成员及隔离回调入口，不冒充已通过 |

只保存脱敏截图、精简报告、命令退出码和必要哈希；不保存 trace/HAR、Cookie、JWT、Secret 或真实报告。测试完成、隔离联调、真实企微验收、合并和生产是不同状态。

## 单次认证诊断最终结果（2026-10-18）

上文“待收”是放行时的历史状态，以下为本轮终态。fixture-auth-diag-r1仅运行一次，三次OAuth原DCL9000ms与exchange均通过，密码/跨页切换通过；未复现原r4超时。一次真实back未观察到persisted，partial/exit2保留，未模拟/重跑，不补判原第八组。

后台实际global engine与get_db隔离证明通过；59表保护摘要前后完全相等，仅既定auth窄豁免。used3、unexpected identity0、服务审计/v7零新增、public_unchanged=true。API19.52秒/guard32.57秒正常停止，三只指定WeCom容器exited且无OOM；client34848/relay42632退出，18000/18443无监听。保留一次my-tasks ERR_ABORTED和代理守卫拦截，不能称所有请求均无失败。

证据为admin/output/wecom-technician-20261017/resume/fixture-auth-diag-r1/closed-result.json，SHA256 bebade660888c3dd8e276f27d383c7e79edc5e1181ff81bfde5d162a72bb9d94；客户端output/playwright/wecom-auth-diag-1792267980089/result.json，SHA256 f2ba3e88915dc25f6054e6c6b131339166cc344ea34b84cba20f0e20380b0090。总控已读并经独立复核接受partial_closed。此前账号限额中断已经恢复，不是各窗口独立额度；技师只读差异补充已交付并核对，CLIENT-AUTH-DIAG-R1-RESULT-v1.md的SHA256为278ceac250dafd4424361e5387f18bea96fd62fb9fc49ea215a515c5540c526f。原问题根因未定，真实BFCache和企微设备验收仍未完成。该轮未改业务、未重建、未动生产库、未提交合并部署。

## AUTH-RETURN-R2 继续授权与验收边界

2026-10-18用户明确要求查清第三次企微登录超时并修好，补齐返回后的缓存恢复。原七组通过证据复用，不启动全量重复测试。保留所有已有未提交修改，不提交、合并、部署或访问生产库；合成隔离库的必要写入必须先冻结精确候选与保护摘要，不涉及生产迁移。

- 后台单写API、共享认证、合成fixture及资源守卫；技师单写专属前端和浏览器驱动；总控单写本记录及看板。先完成双方ready握手再串行启动联调。
- 使用新的合成fixture，只重建原第六/七组的必要前置，保留第三callback的原DOMContentLoaded 9000ms标准。没有实际失败证据前不投机改业务，也不把增加等待屏障称为产品修复。
- 保存脱敏认证导航、表单/导航监听、暂扣v7响应及路由结束时序，区分产品问题与测试驱动干扰。不得导出token、code、state、nonce、Cookie、原始回调URL、HAR或trace。
- 真实返回须区分pageshow.persisted缓存恢复与普通历史重载，记录浏览器版本、启动参数和脱敏缓存拒绝原因。保留产品敏感数据缓存策略，不为命中缓存去掉敏感no-store或模拟生命周期事件。
- 恢复后重新验证当前账号、门店与权限；旧账号资料、草稿和延迟响应不得回流。若安全策略使缓存不可用，安全重载与真实缓存恢复分别判定，不伪称全部通过。
- 沿用已核资源上限与及时停止/独立关闭核验。每轮交付受保护表摘要、精确合成写入、旧记录不变、PID/监听/容器关闭及源码清单哈希。
- 本节仅记录授权与验收条件；根因、修复和实际通过结论以新一轮终态证据补充，不能沿用原r4或缩小诊断冒充本轮通过。

## AUTH-RETURN-R2/R3 终态与环境对照边界

2026-10-18，总控独立核读 R3 客户端结果及后台关闭回执并复算 SHA256。保留所有旧失败，不把新版校验器追溯用来改判 R2。

- R2 复现第三 callback 的 DCL 9000ms 超时。后台 fixture 错把原生 `tech-finish-613-UUIDv4` 键要求成裸 UUID，保护核验失败并提前结束；不能称全部允许字段通过。R2 已安全关闭，其失败回执保留。
- R3 仅把客户端变量改为保留已完成的一次性 v7 handler、不执行 unroute；第三 callback 仍超时，故该假设未获支持。新增传输观测不改响应、权限或业务逻辑。
- R3 callback 的上游 303、fulfill/dispose 均完成，CDP 观察到 complete 文档重定向请求；此后未观察到对应守卫处理、本地终端收件、文档提交或 exchange。不能把 CDP 发起事件当作服务器已收到请求，也不能判定尚未加载的 complete 页面逻辑有错。
- R3 后台 59 张保护表、精确允许的 613 finish/v7/profile/transition/audit 值与 public 摘要通过。认证 used2/ready1、意外身份 0；第三 callback 15.263ms，服务器没有第三次 exchange。保留正常的两次已通过 OAuth、脏表单清除及迟到 v7 跨号保护证据，不扩大为返回恢复或真实企微通过。
- R3 API 29.31 秒、守卫 42.38 秒正常关闭；最低可用内存 2393956352 字节、磁盘 3605884928 字节、PSI 0、OOM 0。三只指定容器 exited，所属客户端/relay PID 已退出，18000/18443 无监听。生产写入 0。

证据（各端本机输出仅作本轮隔离证据，未提交主干）：

- 技师 `output/playwright/wecom-auth-return-r3-1792293561187/result.json`，SHA256 `d36e57a71632e095445e2c096c68e7249402ce9c78da82a38c39a5c12c979320`。
- 后台 `output/wecom-technician-20261017/resume/fixture-auth-return-r3/closed-result.json`，SHA256 `6af89407a94e7c1881d86e824acbbdd6b17a37117909e86b7e7af9fdee0e8284`。
- R2 失败关闭回执 SHA256 `c26aba453e02bc035106fa47172615dd69cdd082af12a5b3317f5d52abede679`，不回改为通过。

R3 实际 Edge 141.0.3537.85，Playwright 1.62.1 的固定元数据对应 Chromium 151.0.7922.34/revision1234。版本兼容性是待验证线索，不是已证实根因。后续只允许在仓库外缓存安装匹配引擎，保持固定依赖、9 秒标准、敏感 no-store、精确 API 写入范围与服务器资源门禁；不更新用户日常浏览器，不重建产品，不重复七组验收。匹配引擎结果与真实后退结果另行追加，不能提前声明修复。

用户已允许本机单实例轻量浏览器在 1.6–1.8 GiB 可用内存下受限尝试；这不是满量构建或服务器资源门禁的豁免。

## AUTH-RETURN-R4 结论与 R5 资源暂缓

2026-10-18 13:12（Asia/Shanghai）。R4 固定 Chromium 151.0.7922.34 仍在第三 callback 后 9 秒超时，未到 back，说明版本不匹配不能单独解释原故障。后台 59 表及允许写入精确值/public 保护通过，API 33.36 秒/guard 46.8 秒正常关闭，最低可用内存 2384183296 字节、磁盘 3602706432 字节、PSI/OOM 为 0。三指定容器退出，所属 PID 与 18000/18443 监听清零。后台 closed-result SHA256 `b1a9f496226616fec7f129f70d011d2f5719d29926e01c69efe6403db9750d7f`；客户端结果 SHA256 `27d2155b126b3b79e1400ab81acccce91e343a1c236cf130f448414d04b4ae81`。

总控和技师定向审查发现本机测试代理 upstream 闲置 5 秒 destroy 后没有关闭下游浏览器 socket。纯 Node 合成 HTTPS 回归复现：callback 303 后，复用死隧道的目标文档超时。仅增加 `upstream.on('close', () => socket.destroy())` 后同一测试目标 200、连接池建立新连接；外域仍 403、反向主动关闭回归通过。未启动浏览器/API/PG，TLS/SPKI、allowlist、闲置超时均未放宽。证据 `PROXY-IDLE-R5-RED-GREEN-v1.json` SHA256 `33d3433f5a0b2c6a7f81d0af442818dd74b59f8e2a9893260d2ca5c8dac4dcd6`。这是测试工具修复，不是生产业务修改；原完整场景是否解决仍待最终集成。

R5 候选已冻结且未消费：客户端 entry `1b5f4a3daa6fa29ce951eab0e21b1cfa3348a3652af19ed17a9d93a93a8acea4`，11 依赖 manifest `0a248844dfa6fafedaeb65d65063a021e402cd62181b7520cde097bb7baa9e55`；后台 manifest `50f4c2972dddbc682fc3800506e3f1fa0d4722b337ad9b1411efb8672a47dcc7`、fixture `a8fc2c602fcbe690da7a9f57633e77e6c5ae73ada471ea2090402092c987e6b4`。仅单行代理修复，其余 R4 场景和门禁不变；无新 waiting/claim/finished 或运行中的本轮服务。

启动前本机只剩约 638 MiB，13:11:50 总控复核 1013 MiB，低于用户允许的轻量测试 1.6–1.8 GiB 范围。固定隔离 Chromium 路径查得 0 残留进程，没有停止用户程序。已请用户释放资源，禁止无依据降低门禁或让后台开空窗口。恢复后复用冻结 R5 并新鲜前检/唯一握手，不重做已通过合同、构建或旧七组。

既有 React persisted 测试仅合成生命周期与 authorize503，不是实际 BFCache 命中；已有后端门店/在职/身份失效合同也不能冒充浏览器返回组合验收。最终须分别记录第三登录、普通后退安全重载、真实 persisted 及未验项，不能用合成事件或改 no-store 补判通过。

本轮保留所有已有修改；无业务代码改动、提交、合并、部署或生产库访问。技师维护本机工具/专属工作流，后台维护隔离 fixture/后端工作流，总控维护本记录及看板。

## AUTH-RETURN-R5/R6 总控终审

2026-10-18 13:56（Asia/Shanghai）。用户退出闲置程序后，本机资源门禁恢复；总控只核对证据和本记录，不重复实施或重跑已有通过项。以下覆盖上节历史资源暂缓状态，不删除旧失败。

### 原第三次登录超时：已关闭

- R5 唯一传输修复仍是本机代理 `upstream.on('close', () => socket.destroy())`。保持原业务前置、9 秒 DCL、TLS/SPKI、白名单、5 秒闲置限制与固定 Chromium 151，三次 OAuth 均 DCL ready 且实际身份语义 observed，第三次 exchange 成功。根因是隔离测试连接池复用未同步关闭的下游连接，不是已证实的生产企微 API 缺陷。
- 脏记录清除、迟到 v7 响应跨账号清除通过。R5 总体仍 failed：返回驱动按当前 phase 接受中间页迟到 pageshow，在真正返回文档加载前断言 pagehide 快照失败；不能回改该原始结果为全通过。
- R5 后台 59 表保护、允许的精确合成业务写入、认证范围/public 摘要通过；第三 callback 13.432ms、exchange 12.701ms，auth used3、意外身份 0。指定容器/PID/监听已关闭，生产写入 0。
- R5 客户端 `technician/output/playwright/wecom-auth-return-r5-1792301281910/result.json` SHA256 `7f190f9e2385ff301c1fcef1175360b699ef12121b9ed93ce99f7df39678a7b4`；后台 `admin/output/wecom-technician-20261017/resume/fixture-auth-return-r5/closed-result.json` SHA256 `e894c7a7104992be21cdbf552f36d9c05bbf8a2c3f58889567c16c05ccb4b520`。

### 返回定向补测：普通重载通过，真实缓存恢复未验证

- R6 只修测试观察时序：等待 neutral 自身 pageshow，再真实 history 返回；返回事件必须来自 main 且源路径为 today/login/entry，拒绝中间页迟到事件。使用 R5 实际失败事件的纯筛选 RED→GREEN 6 例通过。真实缓存分支使用产品 pagehide 处理后闭包快照，未写 storage journal、未合成生命周期事件、未移除 no-store。
- 客户端最终 entry SHA256 `ac2f2fd5f71a81b08a686d6ef56a29c3c40e3517e62dd3ebbdff4902e9467f21`、13 依赖 manifest `fdfa137084e0b1169eed8e6dbe7acc81779b0c932944b4df7bb0ef4504880961`；后台 manifest `fd727a8e45f138c4da5dde66036e04004d9d38fd0c7e9e3ae6d1b68458816d18`。仅六认证路由，建立一次本人 OAuth 后执行一次真实离开/后退，不再执行结束服务、v7 保存、脏表单或前三次 OAuth。
- 实际 returned today 文档 commit 8276ms、document-init 8307ms、pageshow 8532ms（persisted=false），随后进入登录页。返回前后快照与最终 token/staff/auth-method/header/customer 全 false；普通重载安全登录通过。认证 pending 阶段旧身份内容为空。
- 本轮没有真实 BFCache 命中；CDP 返回 `MainResourceHasCacheControlNoStore`、`JsNetworkRequestReceivedCacheControlNoStoreResource`、`BrowsingInstanceNotSwapped`。这只说明本次未恢复，不能推断所有企微浏览器永久禁用缓存，也不能以既有模拟 persisted 测试代替实际恢复。保持 raw partial/exit2，协议 finished=failed 是非通过状态映射，不是新的产品异常；不追跑或降低安全条件。
- R6 后台 59 表业务保护、公有 schema 摘要通过，业务行/字段豁免 0。只允许 own1401 的 proof 时间和最多两次窄认证记录，实际一次 used、scope_valid=true、意外身份 0、errors=[]。未读取生产库或真实顾客资料。
- API 20.43 秒、guard 33.45 秒正常结束；最低内存 2387189760 字节、磁盘 3600809984 字节、PSI 0/OOM 0。三只指定容器 exited，客户端12728/relay8760退出，18000/18443无监听；固定隔离 Chromium 路径残留 0。
- R6 客户端 `technician/output/playwright/wecom-auth-return-r6-1792302734678/result.json` SHA256 `b31c2285bc712660ab9c99a29ef104d1daf238e696c3a2124344457c61559b71`；后台 `admin/output/wecom-technician-20261017/resume/fixture-auth-return-r6/closed-result.json` SHA256 `31d1d95613264646fa1ed56c24bc971b2ee0ec43a143711dab514d066b62457c`。上述路径均相对本机 `C:/Users/gaoji/Documents/ChatGPT/hxy-diy-worktrees/`，仅隔离证据，不是主干事实。

### 剩余边界

真实企微账号/设备、实际 BFCache 恢复及恢复后成功重验仍未现场验收；R6 auth-only 没有新加载顾客档案或新建脏业务表单，不扩张为这些场景通过。原模拟生命周期、后端权限合同与既有业务七组各自保留证据但不互相替代。当前没有新增业务缺陷证据需要改产品；不继续重复测试、不移除敏感缓存策略、不重启生产。保留已有业务修改与全部失败回执，先不提交、不合并、不部署，生产数据库相关仍另行确认。
