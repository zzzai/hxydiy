# 技师端与员工工作台工作状态

# 2026-08-29 智慧宝后台只读审计与 DIY 对接字段基线

## 本地完成

- 使用用户提供的智慧宝后台地址和本地凭据完成已有会话核验；凭据未写入项目文档、日志或回复。
- 只读查看员工管理、房间配置/房间状态、顾客配置/顾客查询和项目设置页面。
- 在架构文档补充智慧宝字段基线、外部门店 ID 稳定键规则及 `contract_pending` 未确认字段清单。

## 涉及文件

- `docs/architecture/hxy-diy-admin-platform-architecture.md`
- `docs/WORK-STATUS.md`

## 测试结果

- 本轮仅更新文档并进行智慧宝后台只读核验，未修改业务源码，未执行管理端/后端测试或生产构建。
- 未执行智慧宝新增、编辑、删除、改价、上下架、开房、派钟、结算或物理资源操作。

## 发布状态

- 未发布生产；服务器、数据库和生产 `current` 未修改。
- 本轮只读核对服务器实际 `current`：`/root/hxy-diy-20260811/releases/customer-profile-member-no-coupon-20260829-1`。
- 真实源码目录当前未检测到 Git 仓库，无法提供源码 `git diff` 或提交记录；未执行清理、回滚或发布。

## 尚未完成事项

- 智慧宝 API 文档、认证方式、二维码绑定、技师派钟关系、履约单 ID、开房/离位/清洁事件、游标和限流规则仍待对方提供并完成 Mock/真实联调。

# 2026-08-29 DIY 管理后台与门店运营后台生产级 PRD/项目规划

## 本地完成

- 新增总 PRD：`docs/product/hxy-diy-admin-platform-prd.md`。
- 新增技术架构与接口契约：`docs/architecture/hxy-diy-admin-platform-architecture.md`。
- 新增分阶段实施、测试、发布和风险计划：`docs/plans/hxy-diy-admin-platform-delivery-plan.md`。
- 固化总部管理员、门店店长、技师三类角色及门店隔离规则。
- 固化总部维护目录、店长仅上下架、店长维护本店技师/服务位/二维码、技师同城跨店只读范围和当前门店写入规则。
- 固化阿里云 OSS 生产媒体方案、智慧宝只读拉取边界、会员价格快照和服务单状态机。
- 固化 7 个实施阶段、阶段退出条件、测试矩阵、生产 SLO、备份/回滚和现场验收门槛。

## 涉及文件

- `docs/product/hxy-diy-admin-platform-prd.md`
- `docs/architecture/hxy-diy-admin-platform-architecture.md`
- `docs/plans/hxy-diy-admin-platform-delivery-plan.md`
- `docs/WORK-STATUS.md`

## 测试结果

- 本轮仅完成文档和规划，不修改业务源码。
- 未执行管理端测试、后端测试或生产构建；待阶段 0/阶段 1 开发后按计划执行。

## 发布状态

- 未发布生产。
- 未进行数据库迁移、OSS 配置、智慧宝真实联调或线上切换。

## 尚未完成事项

- 智慧宝尚未提供 API 文档、测试账号和字段契约，当前只能使用 Mock。
- 商品/项目后台完整编辑、OSS 上传链路、媒体库、引用保护和门店发布模型尚未实现。
- 多店 RBAC、跨店技师授权、服务单命令幂等和数据库级隔离仍需按阶段实施。
- 真实接口联调、备份恢复、性能、断网、并发和门店现场验收尚未完成。

# 2026-08-29 顾客端足部精修项目视觉素材

## 本地完成

- 核对后端正式项目编码为 `hxy-foot-refine-1`，顾客端新增专属主图资源并接入 `projectImage()`。
- 顾客端详情视觉新增足部精修专属说明，使用清洁、修整等非医疗化表述。
- 顾客端测试：`151 passed / 0 failed / 1 skipped`（共 152 项）。
- 顾客端生产构建成功：Vite 转换 `2013` 个模块。

## 素材与生成状态

- 主图由已配置的 `gpt-image-2` 图像网关生成，已视觉检查并保存为 `diy-web/public/assets/projects/hxy-foot-refine-1.webp`。
- 详情区暂复用同风格主图，另存为 `hxy-foot-refine-1-detail.webp`，避免线上出现破图；网关当前对新的竖版请求出现连接中断，待接口恢复后替换为独立 2:3 详情图。

## 发布状态

- 本轮仅完成本地素材与代码接入，尚未发布生产。

# 2026-08-29 顾客端会员个人中心券接口隔离修复（已发布生产）

## 本地完成

- `ProfilePage` 在会员身份下不再请求优惠券接口；个人中心仅加载服务记录与到店记录，避免券接口权限错误导致整体“请求失败”。
- 取消服务单后的刷新调用同步传入会员身份，保持同一分支逻辑。
- 顾客端测试：`151 passed / 0 failed / 1 skipped`（共 152 项）。
- 顾客端生产构建成功：Vite 转换 `2013` 个模块。

## 已发布生产

- Release：`customer-profile-member-no-coupon-20260829-1`，以服务器 `admin-refine-lazy-20260829-1` 为基线，仅替换 `diy-web/dist`。
- 服务器 Manifest SHA-256：`0e82e7e87bbf9ffd7990f5683b99005442f09ea0d6cd8ca147bf35c8dadd5af4`；切换后逐文件校验通过。
- API 容器使用既有生产 `.env` 重建，当前运行状态 `running`、重启次数 `0`；公网 `/api/v1/health` 返回 `status: ok`。
- 无缓存顾客端入口加载正常，项目列表与服务位页面无白屏。

## 待现场验收

- 已以无缓存生产地址打开 6 号沙发；使用授权会员账号完成会员登录（手机号和验证码未记录）。
- 个人中心服务记录显示正常空状态，到店记录成功加载历史记录（共 40 条）；页面无“请求失败，请稍后重试”。
- 会员态未出现“我的券”“领券”或“领取优惠券”入口；顶部显示年度会员身份，菜单价格切换为会员价，门店价删除线保留。
- 本轮未提交真实订单，仅发送授权登录验证码并读取个人中心数据。
- 多设备并发、断网恢复、超时释放、技师确认/结束、画像与评价仍需门店现场闭环。

# 2026-08-29 顾客端提交成功页价格修复（本地完成，待发布）

## 本地完成

- 提交成功页底部金额统一使用按当前会员身份解析后的 `payableTotal`，不再直接读取历史 `pricing_snapshot.payable_total_cents`，避免会员显示门店总价或旧单项金额。
- 新增回归测试 `diy-web/tests/submitted-price-markup.test.ts`，覆盖成功页金额绑定。
- 待发布前重新执行顾客端全量测试、生产构建、发布包 Manifest 校验及线上无痕复核。

## 发布状态

- 本次修复尚未切换服务器 `current`；线上继续运行上一已验证 release。


# 2026-08-29 顾客端动效与选购流程复核

## 本地完成

- 顾客端全量测试：`149 passed / 0 failed / 1 skipped`。
- 顾客端生产构建成功：Vite 转换 `2013` 个模块，主 bundle 约 `416.65 kB`（gzip `129.56 kB`）。
- 回归覆盖详情进入/返回、当前项目价格与整单底部价格隔离、已提交会话追加草稿清理、刷新不恢复旧草稿、会员/非会员价格展示、服务位绑定和轻动效约束。

## 已发布生产验证

- 通过独立 Playwright 会话打开生产顾客端，页面非空，标题为“荷小悦 · 到店选项目”。
- 根门店入口可正常选择服务位；服务位二维码入口能显示对应沙发号，已有设备绑定时不会静默串位。
- 详情页顶部展示当前项目基础价，底部展示当前项目配置价；加入项目后底部才显示整单预计合计，价格上下文未混淆。
- 生产 API 健康接口返回 `status: ok`；最近 30 分钟 API 日志请求均为 200/预期 401/403/409，未发现 5xx。

## 发布状态

- 本轮未切换服务器 `current`，未提交真实营业选单；线上当前 release 仍为 `technician-profile-quick-note-20260829-1`，其中已包含顾客端既有静态资源。

## 待现场验收

- 仍需门店授权手机完成真实会员短信、双设备并发、断网恢复、超时释放、技师确认/结束与画像查询。
- 提交给前台属于真实业务写入，需在指定测试服务位和测试订单范围确认后再执行。

## 2026-08-29 技师服务参考快记生产级契约加固（本地完成，未发布）

### 本地完成

- 按 `docs/product/technician-profile-quick-note-production-prd.md` 补齐技师服务结束后的手机快记：首屏保留记录来源、年龄段、性别、体型、职业场景、服务关注、力度偏好和服务注意事项；保存中防重复，失败保留内容并可使用同一幂等键重试，完成服务后自动打开快记抽屉。
- 后端新增画像 `source`、`idempotency_key` 字段和唯一约束；技师写入强制关联本人完成服务、门店和登录身份，禁止代填/更正；技师读取顾客历史画像返回 403；旧通用画像路由改为店长专用。
- 服务端对白名单基础字段、预设标签、来源枚举、医疗诊断词和空记录进行校验；审计记录来源、幂等键、服务关联和标签摘要，不复制备注全文。
- 新增 Alembic 迁移 `20260829_tech_profile_note`，当前迁移脚本单一 head 为该版本；本地数据库未执行升级（现有本地数据库未处于最新 head）。

### 涉及文件

- `hxy-server/app/api/admin_v2.py`
- `hxy-server/app/models/customer_profile.py`
- `hxy-server/alembic/versions/20260829_technician_profile_quick_note.py`
- `hxy-server/tests/test_technician_profile_quick_note_contract.py`
- `hxy-server/tests/test_customer_profile_records_api.py`
- `hxy-server/tests/test_profile_record_contract.py`
- `hxy-server/tests/test_technician_portal_api.py`
- `admin-react/src/api.ts`
- `admin-react/src/technician/TechnicianProfileSheet.tsx`
- `admin-react/src/technician/TechnicianTodayPage.tsx`
- `admin-react/src/technician/technician-mobile.css`
- `admin-react/tests/technician-workspace.test.ts`

### 测试结果

- 后端画像/技师专项：`21 passed`（包含技师来源必填边界）。
- 技师工作台前端契约：`5 passed`。
- 管理端生产构建：成功（Vite `3997 modules transformed`）；存在既有单 bundle 体积警告。
- Alembic `heads`：`20260829_technician_profile_quick_note`；`alembic check` 因本地数据库尚未升级到最新 head 未通过，未作为发布依据。

### 发布状态

- 尚未发布生产；服务器实际 current 仍以线上 `customer-a11y-20260829-1` 为准，本轮未执行数据库备份、迁移、静态资源切换或 API 重建。

### 待发布/现场验收

- 发布前需在服务器 current 基线执行数据库备份、迁移演练、Manifest 校验、构建产物发布、API 健康检查和回滚确认。
- 需用门店授权手机完成“顾客提交 → 技师确认服务 → 服务结束 → 快记保存/重试 → 审计核对”闭环；真实会员、多设备并发、断网恢复和智慧宝并行操作仍待现场验收。

## 2026-08-29 顾客端生产复核与菜单名称收口

### 本地完成

- 顾客端回归测试：`npm test`，`139 passed / 0 failed / 1 skipped`；启用 `HXY_PRODUCTION_SMOKE=1` 后线上冒烟为 `139 passed / 0 failed / 1 skipped`。
- 顾客端生产构建成功：Vite 转换 2013 个模块，构建产物为 `index-BqRRcyTE.js`、`index-D23x8l6H.css`。
- 后端顾客链路专项：服务位释放、调度器、选单价格、技师状态和顾客画像共 `80 passed`。
- 按最新菜单表修正顾客端“局部调理”硬编码为“局部推拿”，列表、详情、无障碍标签统一从项目名称读取，并新增回归测试。

### 已发布生产

- 线上静态资源与本地最新构建逐文件 SHA-256 一致，当前入口加载 `index-BrN23PiS.js`。
- 新 release：`customer-menu-label-20260829-3`；以线上 `customer-service-copy-20260828-1` 为基线，仅替换顾客端静态资源，未执行数据库迁移。
- 发布过程中发现一次归档目录层级错误，已废弃错误 release `customer-menu-label-20260829-1/2`，最终 release 重新打包、Manifest 校验、镜像构建和 API 重建均通过。
- 当前线上入口加载 `index-BrN23PiS.js`，无痕复核确认项目列表和详情均显示“局部推拿”，控制台错误为 0。
- 无痕移动端只读复核通过：5 号沙发二维码进入后服务位标题保持正确；详情顶部显示当前项目基础价，底部显示当前项目配置价，未带入整单总价。
- 线上项目接口返回正式菜单 13 项；草本泡脚、草本沐足、招牌草本沐足、荷小推、两档精油 SPA、功夫调理及更多服务价格与最新菜单表一致。
- 线上 API 健康接口和顾客端入口均返回 200；本轮未提交真实营业选单、未发送短信、未修改服务位状态。

### 待现场验收

- 真实会员短信登录及会员最低价切换仍需门店授权手机号与验证码，不能以匿名会话替代。
- 多设备并发、跨设备断网恢复、超时释放现场观察、技师确认/结束和画像查询仍需门店手机完成；自动化回归不等于营业验收。
- 线上 6 号服务位当前显示临时占用，现场继续测试前需由授权人员确认其测试状态，避免影响营业。

## 2026-08-28 菜单价格有效期与功夫调理空价格修复

### 本地完成

- 正式菜单保持 SPA 名称“舒享精油 SPA”“深享精油 SPA”不变；功夫调理门店价/团购价为空，仅会员价 980 元。
- `PriceBook` 增加 `effective_to` 有效期字段，历史价格保留但失效版本不再参与顾客端、订单、会员计价和管理端当前价读取。
- 菜单同步脚本遇到新表空价格时关闭旧当前版本，不删除价格历史；恢复价格时追加新的有效版本。
- 顾客端测试 `136 passed / 1 skipped`，生产构建成功；后端菜单同步、价格和会员计价专项通过。

### 已发布生产

- 生产 release：`/root/hxy-diy-20260811/releases/price-book-effective-20260828-2`。
- 发布前数据库备份：`/root/hxy-diy-20260811/backups/pre-price-book-effective-20260828-134433.dump`，SHA-256 `52de9f19f4f4671420f1fb97c798f088f0ef7b3f7d857ed9bb199c03d27c7dbf`。
- Alembic 已执行至 `20260828_price_book_effective_to`；Manifest SHA-256 `570e64ed9fcaa21f1ed89937a6c5c6e80b2d3c15905be59845b6b6fcf56ba86d`。
- 公网 H5、健康接口和项目列表返回 200；线上 13 项菜单价格逐项与新表一致，功夫调理仅显示会员价。

### 待现场验收

- 使用门店授权账号复核功夫调理在顾客端、前台结算参考和会员身份下均不显示门店/团购价。
- 继续进行多设备并发、断网恢复、技师状态同步和智慧宝并行操作现场验收。

## 2026-08-28 会员手机号无痕生产验收

### 已发布生产验证

- 在全新 Playwright 内存会话中完成真实短信验证码登录；手机号和验证码未写入文件或日志。
- 登录成功后顶部入口变为“我的”，个人中心显示“荷小悦年度会员 / 年度权益卡会员”，并保留“退出登录”按钮。
- 会员登录后推荐区不再显示年度会员卡、泡脚月卡或领券入口；仅保留项目推荐。
- 项目列表 12 项均以会员价为主价格，门店价灰色删除线；示例：草本泡脚 `会员¥29.9`、门店价 `¥39.9`，草本沐足 `会员¥69`、门店价 `¥89`。
- 进入草本泡脚详情并加入本次服务后，底部显示“会员价 ¥29.9 / 门店价 ¥39.9”，加购项同步显示会员价；刷新后会员身份和价格保持不变。
- 浏览器控制台错误数为 0；本轮未提交真实营业服务订单。

### 待现场验收

- 仍需门店确认会员账号在多设备并发、提交后技师服务状态同步、服务结束评价和真实结算环节中的一致性；本轮只验证了会员登录、价格和顾客端展示。

## 2026-08-28 全授权顾客端与关键后端回归复核

### 本地完成

- 顾客端生产冒烟：`HXY_PRODUCTION_SMOKE=1 npm test`，`136 passed / 0 failed / 0 skipped`。
- 顾客端关键后端专项：选单、价格、服务状态、评价、技师确认、服务位释放、画像记录共 `96 passed`。
- 后端全量回归：`490 passed / 19 failed / 7 skipped`。19 个失败复核为后台角色迁移契约、已废止物理资源接口状态码、运营历史统计断言和 Alembic head 名称契约；未发现顾客端选购、会员价格、提交追加、服务状态链路失败。

### 已发布生产无痕验收

- 新建 Playwright 内存会话 `fullauth`、`fullauth2`，未使用历史 Cookie、LocalStorage 或缓存。
- 7 号与 6 号二维码分别进入，两会话标题和详情服务位保持各自编码，无串位。
- 6 号会话进入草本泡脚详情，当前项目价格显示门店价 `¥39.9`、会员参考价 `¥29.9`；局部加强显示 `0/2`，拔罐/刮痧显示按次计费。
- 6 号会话断网出现“网络已断开，恢复后将继续同步”；恢复在线后提示消失，页面和详情选择保持可用。
- 提交后返回菜单、刷新、查看清单和进入另一项目追加流程已在前一无痕会话完成，未出现已提交项目回填底部或项目详情显示整单总价。

### 待现场验收

- 真实会员短信登录、会员最低价切换、技师确认服务/结束、超时释放、技师画像写入、跨设备并发和智慧宝并行操作仍需门店授权测试账号与服务位完成；自动化无痕会话不能替代真实营业验收。

## 2026-08-28 顾客端无痕生产提交后返回与刷新验收

### 本地完成

- 基于已发布的顾客端 `customer-seat-switch-20260828-1`，使用 Playwright 全新无痕会话复核提交后状态流转。
- 本轮未新增源码改动；验证重点为提交成功页、返回项目列表、刷新恢复和已提交清单的状态边界。

### 已发布生产

- 线上入口：`https://diy.hexiaoyue.com/?store=1&seat=sofa-08&source=store_qr`。
- 线上入口当前返回 `200` 并加载顾客端静态资源 `index-Dbadxy5R.js`；健康接口返回 `status: ok`，项目接口返回正式菜单 12 项。
- 无痕会话从 8 号沙发二维码进入，选择草本泡脚后提交；成功页正确显示“已提交前台”、8 号沙发和本次服务明细。
- 点击“返回项目列表”后，页面显示“已提交前台，可查看本次清单”，底部新增选购草稿为空，不会把已提交项目重复计入底部。
- 刷新后仍保持 8 号沙发绑定；已提交状态和“查看清单”入口保留，底部选购栏仍为空。
- 打开“查看清单”可看到已提交的草本泡脚，金额为门店价 `¥39.9`；浏览器控制台错误数为 0。
- 从已提交清单返回菜单后重新进入“草本沐足”，详情页只显示当前项目门店价 `¥89` / 会员价 `¥69`；加入后底部新增草稿显示 `¥89`，没有把已提交的草本泡脚合并进当前项目价格。
- 顾客端回归测试：`npm test -- --runInBand`，`136 passed / 0 failed / 1 skipped`；生产构建 `npm run build` 成功，产物 `index-DebsI3ec.js`。

### 待现场验收

- 本轮使用匿名测试会话，未验证真实会员短信登录、技师确认服务、服务结束、并发、断网跨设备恢复、超时释放和技师画像。
- 以上场景仍需门店授权测试服务位和测试账号完成现场验收，自动化无痕验证不能替代真实营业验收。

## 2026-08-28 顾客端会员整单价格快照修复

### 本地完成

- 根因：已提交会话恢复时，顾客端直接读取快照顶层 `member_total_cents`；历史快照可能把单个项目金额（如 67 元）写入该字段，导致底部整单会员价错误。
- 新增 `resolveMemberTotalCents`：无促销时优先使用 `member_subtotal_cents`，缺失时汇总会员明细行；有促销时保留服务端最终 `member_total_cents`，避免覆盖真实减免。
- 会员身份下的只读应付总价和非会员的会员参考价统一使用同一快照解析结果，修复 613 元门店合计显示 67 元会员价的问题；正确会员合计为 413 元，差额 200 元。

### 验证结果

- 顾客端全量测试：`npm test`，当前通过（含新增会员总价回归用例），1 条既有生产冒烟用例按环境跳过。
- 顾客端生产构建：`npm run build` 成功，Vite 转换 2013 个模块。
- 本轮未修改后端、管理后台或技师端；尚未发布生产。

### 待发布与现场验收

- 发布前需用生产发布流程构建并逐文件校验顾客端静态包，再进行线上移动端验证：多项目门店合计 613 元、会员合计 413 元、预计节省 200 元，刷新后金额保持一致。
- 现场仍需使用门店授权会员账号和测试服务位验收真实登录、提交及价格展示；本地自动化不能替代现场验收。

## 2026-08-28 技师账号生命周期生产发布

### 本地完成

- 完成技师账号生命周期闭环：店长邀请/首次激活、重置密码、停用、恢复、离职、返聘；停用和离职递增 `credentials_version`，立即使旧 JWT 失效。
- Staff 与 Technician 继续保持独立对象，通过 `technician_id` 一对一关联；技师档案禁止物理删除，旧删除接口返回 `TECHNICIAN_PHYSICAL_DELETE_FORBIDDEN`。
- 管理端技师列表补充登录状态、账号名、凭证版本和邀请有效期；所有生命周期写操作保留门店校验、幂等键和审计记录。
- 生产专用迁移从线上当前 head `20260826_technician_portal` 继续，新增 `staff.credentials_version`、`technician_invites.purpose` 及用途约束；未把本地未验收的角色归一化和其他开发迁移带入生产。

### 涉及文件

- 后端：`hxy-server/app/api/admin.py`、`hxy-server/app/api/admin_v2.py`、`hxy-server/app/api/technician.py`、`hxy-server/app/api/technician_admin.py`、`hxy-server/app/models/core.py`、`hxy-server/app/models/technician_portal.py`
- 管理端：`admin-react/src/api.ts`、`admin-react/src/core/auth/permissions.ts` 及 `admin-react/dist`
- 测试：`hxy-server/tests/test_technician_account_lifecycle.py`、`hxy-server/tests/test_alembic_contract.py`、`admin-react/tests/auth.test.ts`、`admin-react/tests/technician-account-lifecycle.test.ts`

### 测试结果

- 技师账号生命周期与迁移专项：`15 passed`；技师/画像/权限专项：`24 passed`；发布脚本/迁移契约：`19 passed、3 skipped`。
- 管理端全量测试：`83 passed`；管理端生产构建成功，Vite 仅保留既有单 bundle 大于 500 KB 警告。
- 后端全量：`490 passed、19 failed、7 skipped`。失败集中在既有角色迁移契约、已废止物理资源接口和历史测试夹具，不属于本轮账号生命周期；未以全量通过作为发布依据。
- 发布前数据库备份：`/root/hxy-diy-20260811/backups/pre-technician-account-lifecycle-20260828-153132.dump`，363 KB，SHA-256 `69f0b9523120ba3fc41cba447eafd0e3266fc90236a9c0994e9f662841701a78`。
- 隔离恢复库迁移演练通过，迁移 head 为 `20260828_tech_acct_lifecycle`，字段和约束已核对。

### 已发布生产

- 生产 release：`/root/hxy-diy-20260811/releases/technician-account-lifecycle-20260828-2`。
- 发布基线为服务器发布前实际 `customer-append-flow-20260828-1`，保留顾客端最新内容；仅叠加技师账号生命周期后端、生产兼容迁移和管理端构建。
- 当前 `current` 已原子切换到本 release；Manifest 全量校验通过，SHA-256 `4ad7f50917c601de927eca987e1f8d320e7f04838093b03336462c9ffe16164e`。
- API 容器重建后 `running`、重启次数 `0`；线上 `alembic current` 为 `20260828_tech_acct_lifecycle`；公网健康接口、`/admin/`、`/technician/` 均返回 200。
- 线上未授权检查：技师任务、技师个人信息、技师管理列表、请假列表均返回 401；错误密码登录返回 401。手机视口验证 `/technician/` 自动进入 `/technician/login`，显示账号密码、登录和首次激活/重置入口。

### 待门店现场验收

- 店长使用门店授权测试技师完成“邀请/激活 -> 手机登录 -> 查看沙发/房间任务 -> 确认服务 -> 服务结束 -> 顾客画像记录”，并在管理端验证账号状态和审计记录。
- 验证“重置密码/停用后旧会话立即失效、恢复后可重新登录、离职保留历史数据且不可物理删除”。
- 本次未对真实营业订单执行确认服务、结束服务或画像写入；现场验收必须使用门店授权测试服务位和测试订单。

## 2026-08-28 顾客端提交后追加选购修复

### 本地完成

- 修复提交后台后返回菜单无法进入项目二级页继续选择的问题：`submitted` 会话在服务位仍为 `held`、`waiting_service` 或 `in_service` 时允许顾客追加选购；服务结束、清洁、释放、取消和过期状态仍保持只读。
- 提交成功返回菜单或刷新时继续使用空白追加草稿，不把原已提交服务重新显示到底部选购栏。
- 再次提交追加项目时，前端将当前追加草稿与服务器原已提交项目合并：相同项目/偏好/加购合并数量，不同偏好保留独立服务行，新茶饮替换旧茶饮，避免覆盖原订单。

### 验证结果

- 顾客端完整测试：`npm test`，130 passed、1 skipped、0 failed。
- 顾客端生产构建：`npm run build` 成功，Vite 转换 2013 个模块。
- Playwright 本地页面验证未完成：本地 8010 API 预览数据库缺少 `projects.current_published_version_id`，导致项目、服务位等接口返回 500；需先按当前后端迁移/种子流程重建预览库后再执行浏览器闭环。
- 本轮未执行生产部署，未修改管理后台、技师端、后端代码或数据库。

### 待发布与现场验收

- 发布前在正确 schema 的隔离后端环境重新执行移动端流程：提交项目 -> 返回菜单 -> 进入另一个项目 -> 选择偏好/加购 -> 底部显示新增草稿 -> 提交追加，并核对原项目仍保留。
- 通过发布门禁后再由服务器发布；现场需使用授权测试服务位验证提交、追加和服务状态轮询。

## 2026-08-28 技师确认服务预计结束时间与超时释放修复

### 本地完成

- 根因：技师端点击“确认服务”时只写入 `actual_start_at`，没有写入 `expected_end_at`；自动释放策略依赖“预计结束时间 + 30 分钟”，因此该入口创建的服务中占用不会进入超时释放判断。
- 技师确认服务现从已提交选单读取项目与加项时长，写入 `expected_end_at`；无有效时长时以 60 分钟为兜底，不改变智慧宝负责的真实开位、派钟、离位或物理资源管理。
- 新增回归用例验证 70 分钟项目确认服务后，`expected_end_at - actual_start_at = 70 分钟`。

### 验证结果

- 服务状态、服务位占用、自动释放、调度器与选单闭环：`python -m pytest tests/test_technician_portal_api.py tests/test_occupancy_release_policy.py tests/test_occupancy_scheduler.py tests/test_business_closure_state_machine.py tests/test_selection_closure_v2.py -q`，61 passed。
- 会员价格/登录、画像标签与门店隔离、技师权限、双床并行：66 passed。
- 顾客端：`npm test`，125 passed、1 skipped、0 failed；`npm run build` 成功。
- 生产移动浏览器（390×844）：正式服务位二维码进入 6 号沙发后，项目菜单与 12 个正式项目正常渲染；模拟断网出现“网络已断开，恢复后将继续同步”，恢复网络后横幅消失且页面不白屏；控制台无错误。截图：`diy-web/output/playwright/production-timeout-release-menu.png`、`diy-web/output/playwright/production-offline-banner.png`。

### 已发布生产

- 生产 release：`/root/hxy-diy-20260811/releases/technician-timeout-20260828-1`。
- 以生产实际 `customer-service-status-20260828-1` 为基线，仅替换 `hxy-server/app/api/technician.py` 的预计结束时间逻辑，未夹带本地其他未发布后端修改，未执行数据库迁移。
- 发布前数据库备份：`/root/hxy-diy-20260811/backups/pre-technician-timeout-20260828-123050.dump`，SHA-256 `b5822a639624524292490c2e9efe81e869f93496a751d5d2b08eb9982ddb4bad`。
- 新 release Manifest 校验通过，SHA-256 `ea14c34f29658beec1d2ccaec34a0c67b8d81d167776b93a5a22bf7ac3ba0861`；原子切换后 `hxy-diy-api` 重建完成、重启次数为 0，公网健康接口与顾客端入口均返回 200，容器内已确认新逻辑存在。

### 待现场验收与历史数据处理

- 浏览器验证在授权测试服务位 6 号沙发创建临时占位 `#272`，其自然过期时间为 UTC `2026-08-28 04:49:08`。待调度器自然释放后复核状态和审计，未手工删除或绕过业务状态机。
- 已完成自然释放复核：`#272` 在 `2026-08-28 04:49:15 UTC` 自动变为 `released`，版本从 1 变为 2；审计写入 `occupancy_auto_released`，`reason_code=hold_expired`，未执行人工清理。
- 只读复核发现 1、2 号沙发存在旧版本测试遗留的 `in_service` 占用，均缺失 `expected_end_at`，因此不适用本轮自动释放规则。该两条记录需门店确认是否为非营业测试数据后，由授权人员按既定流程处理；本轮没有擅自结束服务。
- 尚未对真实手机号发送短信验证码；会员真实短信登录仍需使用门店授权测试手机号另行验收。

### 本地全量后端测试阻断项

- `python -m pytest -q` 结果为 477 passed、22 failed、7 skipped。该结果不能标记为全量通过。
- 根因一：本地未发布的角色归一化代码已禁止未绑定的 legacy `staff` 角色，但部分旧后台测试仍以 `staff` 身份断言只读访问或临时账号登录成功，导致返回 `ROLE_MIGRATION_REQUIRED`（403）。需要由管理后台/身份模型负责人明确迁移后的“店长、技师、临时员工”测试夹具与权限契约，再统一更新测试；顾客端窗口不直接改变这组后台权限策略。
- 根因二：本地 Alembic 存在 `20260825_staff_expiry` 与 `20260826_coupon_template_store_scope` 两个 head，旧迁移升级契约因 `alembic upgrade head` 的多 head 错误失败。下一轮包含后台/迁移改动的发布前必须创建并验证 merge migration；本轮已发布的最小后端修复不包含这些未发布迁移。
- 其他失败均属于上述权限契约变更或已废止的 DIY 物理资源接口状态码断言，未发现指向顾客端菜单、会员价、二维码选位或本轮预计结束时间逻辑的失败。

## 2026-08-28 顾客端授权生产 E2E 验收

### 已完成

- 门店授权使用测试服务位 `3号沙发` 与测试技师 `tech-1`，完成一次真实生产闭环：顾客扫码 → 选择草本泡脚（老姜、适中力度）→ 提交给前台 → 技师确认服务 → 顾客端同步“服务进行中” → 技师结束服务 → 顾客评价。
- 顾客返回菜单并刷新后，底部选购草稿保持为空，已提交清单保持只读可见。
- 技师确认后顾客端约 1.2 秒显示“服务进行中 / 已开始为您服务”；结束后显示评价入口；提交 5 星“整体放松”评价成功。
- 数据库只读复核：同一选单会话、3 号沙发占用、技师确认/结束审计与评价记录关联一致；门店价 3990 分、会员参考价 2990 分保持一致。
- 详细测试用例与执行证据已写入 `docs/CUSTOMER-FRONTEND-TEST-MATRIX.md`。

### 仍需扩展验收

- 本次证明单次生产 E2E 闭环可用，不代表多门店、多设备、多班次连续营业已全部验收。
- 会员真实登录价格切换、并发抢位、网络中断恢复、服务超时自动释放、技师画像记录和智慧宝并行操作仍需分别使用授权测试数据验证。

更新时间：2026-08-26

## 2026-08-28 顾客端技师确认服务状态同步

### 本地完成

- 根因：顾客端服务状态轮询此前只在 `boot === submitted` 的提交成功页运行；顾客返回项目列表后进入 `ready`，轮询停止，因此无法看到技师确认后的 `in_service`。
- 新增 `diy-web/src/customerServiceStatus.ts`，统一定义轮询条件和顾客可读服务进度文案。
- `diy-web/src/App.tsx` 在已提交/已确认会话的项目列表页继续轮询服务状态，并同步最新选单、服务位和占用状态；保留提交后清空草稿标记。
- 提交成功页和返回菜单后的状态条均读取实时服务状态；技师确认后显示“服务进行中 / 已开始为您服务”，服务结束后提供评价提示。
- 新增 `diy-web/tests/customer-service-status.test.ts` 回归测试，覆盖返回菜单继续轮询、普通草稿不轮询、服务中状态文案。

### 验证结果

- 顾客端完整测试：`npm test`，125 passed、0 skipped、0 failed。
- 顾客端生产构建：`npm run build` 成功。
- 生产冒烟：`HXY_PRODUCTION_SMOKE=1 npm test`，125 passed、0 skipped、0 failed；入口、静态资源和 `/api/v1/health` 均正常。
- 线上脚本已确认包含“已开始为您服务”和“服务中，可查看本次清单”文案；API 容器运行中，重启次数为 0。

### 已发布生产

- 生产 release：`/root/hxy-diy-20260811/releases/customer-service-status-20260828-1`。
- 以服务器实时 `customer-submitted-return-20260827-1` 为基线，仅替换顾客端 `diy-web/dist`；未修改管理端、技师端、后端代码或数据库，未执行迁移。
- 已完成新 release Manifest 全量校验、原子切换和 API 容器重建；公网入口返回 200，健康接口返回 `status: ok`。

### 待现场验收

- 使用门店授权的测试服务位走一次“顾客提交 → 顾客返回项目列表 → 技师点击确认服务 → 顾客端等待不超过 20 秒显示服务中 → 技师服务结束 → 顾客端显示评价入口”。
- 自动化和公网冒烟不替代真实门店营业验收；未经授权不对真实营业订单执行确认服务或服务结束写操作。

## 本地完成

- 在真实源码 `C:\Users\gaoji\WorkBuddy\2026-07-31-12-31-02` 中补齐 `Staff.technician_id` 显式一对一关联，以及技师邀请、激活、登录、请假审批、离职停用和审计。
- 新增技师本人工作台 API：本人任务查询、仅本人关联服务的“确认服务/服务结束”，使用服务位 DIY 占用状态与幂等审计；服务结束后可填写顾客服务参考；未新增智慧宝开房、派钟、离位、清洁或物理释放能力。
- 技师画像写入增加服务完成、本人技师关联和门店范围校验，避免跨顾客/跨技师越权。
- 管理端新增技师移动工作台页面及 API 客户端，技师角色仅可访问 `/technician`。
- 新增 Alembic 迁移 `20260826_technician_portal.py`。

## 涉及文件

- `hxy-server/app/models/core.py`
- `hxy-server/app/models/technician_portal.py`
- `hxy-server/app/api/technician.py`
- `hxy-server/app/api/technician_admin.py`
- `hxy-server/app/api/admin.py`
- `hxy-server/app/api/admin_v2.py`
- `hxy-server/app/main.py`
- `hxy-server/app/models/__init__.py`
- `hxy-server/alembic/versions/20260826_technician_portal.py`
- `hxy-server/tests/test_technician_portal_api.py`
- `admin-react/src/api.ts`
- `admin-react/src/auth.ts`
- `admin-react/src/layouts/MainLayout.tsx`
- `admin-react/src/pages/TechnicianHomePage.tsx`

## 测试结果

- `python -m pytest tests/test_technician_portal_api.py tests/test_customer_profile_records_api.py tests/test_auth_boundary_p0.py -q`：11 passed。
- `npm test -- --runInBand`（管理端）：56 passed。
- `npm run build`（管理端）：成功；Vite 仅提示单 bundle 大于 500KB。
- `python -m alembic heads`：单一 head `20260826_technician_portal`。
- 已在生产数据库创建备份：`/root/hxy-diy-20260811/backups/pre-technician-portal-20260826-154752.dump`，SHA-256 `f2b10e0d6a3121d5ccb5fb705a9621f887807dd7a8e717a928db58058f43750f`。
- 旧版闭环/迁移组合测试在本地执行超过 30 秒未返回最终摘要，尚未把它们视为通过。

## 发布状态

- 已发布生产，当前 release 为 `/root/hxy-diy-20260811/releases/technician-portal-20260826-4`。
- 已完成生产数据库备份、隔离恢复、迁移、schema 漂移检查、Manifest 校验、原子切换和健康检查。
- 已基于门店现有模拟技师档案创建测试账号：用户名 `tech-1`，初始测试密码已通过受控激活流程设置，不在文档中明文保存。
- 线上已验证管理员邀请、技师激活、技师登录、本人工作台和任务查询；当前无待处理任务。

## 待门店现场验收/待完成

- 由门店提供测试服务单，继续验收确认服务 → 服务结束 → 顾客画像 → 审计完整链路。
- 确认邀请通道、请假政策、离职生效时间和真实智慧宝履约单关联后，再决定是否灰度发布。

## 2026-08-26 顾客端分类导航本地验证

- 顾客端左侧分类统一为六项：茶饮、泡脚沐足、推拿、精油 SPA、养生小项（含局部调理）、功夫套盒；保留单字圆圈标识。
- 分类点击改为只滚动右侧 `.catalog-main`，不带动外层页面；增加 `aria-current` 与左侧可视区自动跟随。
- 右侧滚动高亮改用容器滚动位置计算，修复短分区交界处高亮误跳及最后分区到底无法命中的问题。
- 本地顾客端测试：110 passed，1 skipped；生产构建成功；Impeccable layout detector 无新增问题。
- 已通过 Playwright 移动端本地实测：六项点击均保持 `window.scrollY=0`，右侧滚动正确，点击与手动滚动高亮一致。
- 本轮仅本地修改，未发布生产，待用户确认视觉效果后再进入发布流程。

## 2026-08-26 顾客端分类导航生产发布

- 以服务器最新的 `position-board-20260826-1` 为后端/管理端基线，仅替换顾客端 `diy-web/dist`，避免夹带工作区未验收的后端改动。
- 生产 release：`customer-category-nav-20260826-3`；`current` 已原子切换到该版本；未执行数据库迁移。
- API 容器已按新 release 重建，健康接口、项目列表接口通过，容器运行且重启次数为 0。
- 公网顾客端已验证六项分类、右侧独立滚动、外层页面不滚动及 `aria-current` 高亮联动全部正常。
- 发布过程中曾发现并发技师端 release 导致后端 ORM 映射错误并返回 500，已回到稳定后端基线后重新发布；该并发 release 未被回滚，最终版本保留其前一版生产后端/管理端内容。

## 2026-08-26 顾客端详情主图完整显示

- 根因：详情页正方形项目图被 `.mini-detail-hero` 固定为 390×292 并使用 `object-fit: cover`，导致上下内容裁切。
- 修复：详情主图改为 1:1 自适应高度并使用 `object-fit: contain`，保留完整品牌 IP 与场景画面。
- 本地验证：110 passed，1 skipped；生产构建成功；Impeccable 检查无新增问题；本地渲染尺寸 390×390。
- 生产 release：`customer-detail-hero-20260826-1`，以服务器当时最新 `technician-portal-20260826-4` 为基线，仅替换顾客端静态资源；未执行数据库迁移。
- 公网验证：详情主图自然尺寸 1024×1024，渲染尺寸 390×390，`object-fit: contain`，API 健康及项目列表正常。

## 2026-08-26 SPA 菜单与招牌项目优化

- 60 分钟 SPA 生产目录已补齐为与 90 分钟 SPA 相同的三组结构：精油、手法力度、小项加购；通过复制 90 分钟已发布目录生成 60 分钟独立发布版本。
- 两个 SPA 顾客名称调整为「舒享精油 SPA」（60 分钟）和「深享精油 SPA」（90 分钟）。
- 招牌草本沐足项目卡片主图左上角增加金色「招牌」角标，避免遮挡人物主体和加购按钮。
- 修复 `configure_footbath_options.py` 加锁应用阶段遗漏可选 60 分钟 SPA 的缺陷，并新增回归测试。
- 后端相关测试：18 passed；顾客端测试：111 passed，1 skipped；顾客端生产构建成功。
- 生产 release：`customer-spa-menu-20260826-1`；未执行数据库迁移，API 健康、项目列表、容器状态正常。
- 公网核验：两个 SPA 均返回三组选购配置，招牌角标存在且名称已更新。

## 2026-08-26 顾客端详情简介卡片层叠增强

- 线上复核确认简介卡片原本仍有 18px 负边距层叠，但白色背景与主图边界对比弱，视觉上不明显。
- 调整为 24px 负边距、16px 圆角并增加轻微上浮阴影，保持主图完整展示同时强化“主图 → 简介卡片”的层级关系。
- 本地顾客端测试：110 passed，1 skipped；生产构建成功。
- 生产 release：`customer-detail-overlap-20260826-1`，以当前线上版本为基线，仅替换顾客端静态资源；未执行数据库迁移。
- 公网验证：主图底部 444px、简介卡片顶部 420px，实际层叠 24px；API 健康、项目列表和容器状态正常。

## 2026-08-26 技师端导航栏修复

- 根因：技师角色虽有 `/technician` 路由权限，但管理端 `MainLayout` 未配置技师菜单项，导致左侧侧栏为空。
- 修复：新增 `TECHNICIAN_NAV_ITEMS` 导航常量，并在经营分组显示“技师工作台”；未增加智慧宝负责的开房、派钟、离位、清洁或物理资源释放功能。
- 本地验证：管理端测试 57 passed；`npm run build` 成功（仅有单 bundle 大于 500KB 的既有提示）。
- 生产 release：`technician-nav-customer-detail-20260826-1`，以线上 `customer-detail-hero-20260826-1` 为基线，仅替换管理端静态资源；未执行数据库迁移。
- 线上验证：使用 `tech-1` 登录 `/admin/` 后，浏览器实际显示“经营 → 技师工作台”，并打开 `#/technician` 工作台页面；API 容器重建后运行正常。

## 2026-08-26 技师移动端独立工作台

- 产品决策：桌面端技师登录和后台技师导航不再作为正式入口，技师统一使用手机优先的独立 Web：`https://diy.hexiaoyue.com/technician/`。
- 本地完成：新增独立登录、今日服务、服务记录、我的、底部三栏导航、触控服务按钮和服务参考底部抽屉；技师访问 `/admin/` 会被引导到移动端。
- 涉及源码：`admin-react/src/App.tsx`、`src/auth.ts`、`src/api.ts`、`src/technician/*`、`src/pages/LoginPage.tsx`、`src/layouts/MainLayout.tsx`、`tests/technician-mobile.test.ts`、`hxy-server/app/release_static.py`、`hxy-server/tests/test_release_static_files.py`。
- 本地验证：管理端 `npm test -- --runInBand`：61 passed；`npm run build`：成功（仅有单 bundle 大于 500KB 的提示）；后端技师与静态入口测试：10 passed。
- 已发布生产：release `/root/hxy-diy-20260811/releases/technician-mobile-20260826-1`；以服务器 `customer-spa-menu-20260826-1` 为基线，仅更新移动端静态资源和静态入口挂载；未执行数据库迁移。
- 线上验证：`/api/v1/health` 返回 200；API 容器 running、重启次数 0；使用 `tech-1` 登录独立入口后进入 `/technician/today`，显示“今日服务/服务记录/我的”三栏和移动空状态。
- 线上截图：[technician-mobile-production.png](C:\Users\gaoji\Documents\ChatGPT\hxy-diy\output\playwright\technician-mobile-production.png)。
- 待门店现场验收：使用真实服务单完成“登录 → 查看任务 → 确认服务 → 服务结束 → 填写服务参考 → 审计”闭环；确认真实手机网络与门店账号策略。

## 2026-08-26 技师移动端生产 PRD 评审

- 用户确认桌面端技师登录不再作为正式方案，技师端改为手机优先的独立 Web。
- 已使用 `prd-development` 技能评审并完善生产 PRD：
  `C:\Users\gaoji\WorkBuddy\2026-07-31-12-31-02\docs\product\technician-portal-production-prd.md`
- PRD 已补充问题证据、用户画像、成功指标、用户故事与验收标准、权限/门店隔离、智慧宝边界、风险和开放问题。
- 发现并记录旧版 `DIY-TECHNICIAN-PRD-V2.md` 中“本期不建设独立技师工作台”与当前产品决策冲突；新 PRD 明确覆盖该旧条款，但保留智慧宝物理资源边界。
- 当前状态：PRD 待用户审阅，尚未开始移动端代码实施，未发布生产。

## 2026-08-26 技师移动端服务位看板与顾客选单可见性

### 本地完成

- 顾客提交选单后，只要门店服务位存在 `waiting_service`/`in_service`/`post_service_present` DIY 占用，技师手机端即可看到对应服务位；技师端不涉及派单、接单或认领。
- 技师任务 API 增加沙发/房间/床位元数据、选单状态和顾客提交的项目摘要；按门店范围查询，不创建或依赖 Visit、ServiceOrder 或 ServiceAssignment。
- 技师移动首页从纵向任务卡改为“沙发/房间/床位”分组网格；点击服务位卡片打开底部抽屉，查看顾客下单项目，并保留确认服务、服务结束、服务参考入口。
- 服务记录页仅显示当前登录技师实际执行“服务结束”的审计记录，避免把全店共享看板数据误当成本人历史。
- 本店技师可对共享服务位确认服务、服务结束；服务端按门店范围、占用状态、幂等键和审计记录校验。顾客画像仅允许由实际写入服务结束审计的技师填写。

### 涉及文件

- `hxy-server/app/api/technician.py`
- `hxy-server/tests/test_technician_portal_api.py`
- `admin-react/src/technician/technicianMobile.ts`
- `admin-react/src/technician/TechnicianTodayPage.tsx`
- `admin-react/src/technician/TechnicianHistoryPage.tsx`
- `admin-react/src/technician/technician-mobile.css`
- `admin-react/src/api.ts`
- `admin-react/tests/technician-mobile.test.ts`
- `admin-react/src/pages/ReservationsPage.tsx`（删除已隔离旧页面）

### 测试结果

- `python -m pytest tests/test_technician_portal_api.py tests/test_customer_profile_records_api.py tests/test_auth_boundary_p0.py -q`：12 passed。
- `node --experimental-strip-types --test tests/technician-mobile.test.ts tests/navigation-boundary.test.ts`（技师端与边界）：8 passed。
- 管理端完整 `npm test -- --runInBand`：72 passed，1 项既有 `tests/today-page-error.test.ts` 断言未同步当前 `TodayPage` 的 service-order 数据提供器实现；与本轮技师端无关。
- `npm run build`（管理端）：成功；仅有既有单 bundle 大于 500KB 提示。

### 发布状态

- 本轮仅本地修改，尚未发布生产；未执行数据库迁移。

### 待门店现场验收/尚未完成

- 需用真实顾客提交的沙发/房间选单验证手机端看板刷新和抽屉明细。
- 服务位任务为门店共享可见，不存在“派单/接单/认领”状态；本店技师均可对服务位执行确认服务和服务结束。

## 2026-08-27 技师移动端共享服务位看板生产发布

### 本地完成

- 技师端按本店 `waiting_service`、`in_service`、`post_service_present` DIY 占用展示顾客已提交的沙发、房间和床位；点击服务位可查看顾客选单。
- 本店技师可对共享服务位执行“确认服务”和“服务结束”，不创建、不查询、不依赖派单、接单、认领或 `ServiceAssignment`。
- 服务端继续执行技师角色、门店范围、占用状态、幂等键和审计校验；顾客服务参考仅限实际写入服务结束审计的技师填写。

### 涉及文件

- `C:\Users\gaoji\WorkBuddy\2026-07-31-12-31-02\hxy-server\app\api\technician.py`
- `C:\Users\gaoji\WorkBuddy\2026-07-31-12-31-02\hxy-server\tests\test_technician_portal_api.py`
- `C:\Users\gaoji\WorkBuddy\2026-07-31-12-31-02\admin-react\src\technician\TechnicianTodayPage.tsx`
- `C:\Users\gaoji\WorkBuddy\2026-07-31-12-31-02\admin-react\src\technician\TechnicianHistoryPage.tsx`
- `C:\Users\gaoji\WorkBuddy\2026-07-31-12-31-02\admin-react\src\technician\technicianMobile.ts`
- `C:\Users\gaoji\WorkBuddy\2026-07-31-12-31-02\admin-react\src\technician\technician-mobile.css`

### 测试结果

- 后端：`python -m pytest tests/test_technician_portal_api.py tests/test_customer_profile_records_api.py tests/test_auth_boundary_p0.py -q`，12 passed。
- 技师端与边界：`node --experimental-strip-types --test tests/technician-mobile.test.ts tests/navigation-boundary.test.ts`，8 passed。
- 管理端完整测试：`npm test`，75 passed。
- 管理端生产构建：`npm run build` 成功。

### 已发布生产

- 生产 release：`/root/hxy-diy-20260811/releases/technician-position-board-20260827-1`；`current` 已原子切换至该版本。
- 发布基线为服务器实际 `technician-mobile-20260826-1`，仅覆盖本轮 `hxy-server/app/api/technician.py` 和管理端生产静态资源，不包含数据库迁移。
- 发布前数据库备份：`/root/hxy-diy-20260811/backups/pre-technician-position-board-20260827-210215.dump`，348 KB，SHA-256 `8c94c0c61477f4310ecdf679f6b6b36c03a2785146ffadf50dd6e4da2b1948ff`。
- 新 release 的 Manifest 与移动端 JS/CSS 引用已校验；API 容器重建后运行正常、重启次数为 0；`/api/v1/health` 和 `/technician/` 均返回正常。
- 已用 `tech-1` 完成线上登录、技师资料及本店服务位看板只读验证：技师角色、门店范围正确；当时当前门店无待处理服务位。

### 待门店现场验收

- 由门店提供测试服务位，验证“顾客提交选单 → 技师手机端立即看到服务位 → 点击查看选单 → 确认服务 → 服务结束 → 填写顾客服务参考 → 审计记录”的完整写入链路。
- 不在未获门店授权时对真实营业订单执行确认、结束或顾客服务参考写操作。

## 2026-08-27 顾客端项目列表价格层级优化

### 本地完成

- 本轮仅调整顾客端项目列表卡片价格，不改项目详情页、底部选单或结算页。
- 匿名顾客和非会员统一单行显示“当前价 + 会员价”，不再使用“门店价”和“可省”文案；例如 `¥129  会员 ¥89`。
- 会员统一单行显示绿色会员最低价，普通价格置后并使用灰色删除线；例如 `会员 ¥89  ¥129`。
- 价格展示逻辑收敛到 `projectListPricePresentation`，覆盖匿名、非会员、会员三种身份，避免组件内分支漂移。

### 验证结果

- 顾客端完整测试：112 passed，1 skipped，0 failed。
- 顾客端生产构建：成功，Vite 2011 modules transformed。
- Playwright 本地移动端验证：375px、390px、430px 下全部收费项目价格均为单行，无横向溢出，与右侧加购按钮无重叠。
- Playwright 会员态验证：顶部显示“我的”；会员价为绿色主价格，普通价为灰色删除线；页面不显示“领券/领取优惠券”。
- 本地预览：`diy-web/output/playwright/project-list-price-local.png`、`diy-web/output/playwright/project-list-price-member-local.png`。
- Impeccable 检查仅报告项目既有侧边强调线和宽度动画警告，本轮价格代码未新增对应问题。

### 发布状态

- 已发布生产：`/root/hxy-diy-20260811/releases/customer-list-price-20260827-2`。
- 发布以服务器实时 `technician-position-board-20260827-1` 为基线，仅替换 `diy-web/dist`；未执行数据库迁移。
- 发布前后均完成 `MANIFEST.sha256` 校验；当前 Manifest SHA-256 为 `163ed9b655dccdee17ceff51d3ed2f447ffb4ec58e980af1446a0261628743a0`。
- API 容器已重建，状态 `running`，重启次数 `0`；容器内健康接口与公网健康接口均返回 `status: ok`。
- 公网顾客端 H5 返回 200，项目接口返回 12 个项目；线上 Playwright 390px 验证项目卡片价格单行、无“门店价”和“可省”文案、无溢出/遮挡。
- 线上预览截图：`diy-web/output/playwright/project-list-price-production.png`。

## 2026-08-27 技师端全量服务位看板修复

### 根因

- 技师任务接口此前仅返回已有 `waiting_service`、`in_service` 或 `post_service_present` DIY 占用的服务位。门店没有顾客下单时接口返回空数组，移动端因此没有任何沙发或房间区位卡片。

### 本地完成

- 技师任务接口现返回本店全部启用的实际服务位，仅为有有效顾客选单的服务位叠加占用、选单与服务状态。
- 空闲服务位显示“空闲 / 暂无顾客下单”，不显示确认服务、服务结束或服务参考操作；有顾客选单的服务位仍显示下单项目和对应动作。
- 沙发单独分组；房间内床位归入“房间”分组；房间空间容器不作为可操作服务位展示。
- 未增加派单、接单、认领、开房、派钟、离位、清洁或物理资源释放能力。

### 测试结果

- 新增空闲服务位 API 回归测试：`python -m pytest tests/test_technician_portal_api.py -q`，6 passed。
- 技师端与边界：`node --experimental-strip-types --test tests/technician-mobile.test.ts tests/navigation-boundary.test.ts`，8 passed。
- 后端技师/画像/权限测试：13 passed。
- 管理端完整测试：75 passed；管理端生产构建成功。

### 已发布生产

- 生产 release：`/root/hxy-diy-20260811/releases/technician-all-positions-20260827-1`；基线为发布时服务器实际 `customer-list-price-20260827-2`，因此保留顾客端价格版本。
- 发布前数据库备份：`/root/hxy-diy-20260811/backups/pre-technician-all-positions-20260827-213003.dump`，352 KB，SHA-256 `61b62d65d2d8bedcbb07a283bc2d04bf2c5f90cf5df73f314cab66d03d6c6ef5`。
- 线上只读验证：`tech-1` 登录后任务接口返回 17 个服务位，其中沙发 8 个、房间床位 9 个，当前 0 个有顾客订单；Manifest、健康接口、迁移 head 和 API 容器状态均正常，容器重启次数为 0。

### 待门店现场验收

- 请在手机端退出后重新打开或刷新 `https://diy.hexiaoyue.com/technician/`，确认先看到 8 个沙发和 9 个房间床位的空闲卡片。
- 由门店用测试服务位继续验证顾客提交后该区位立即显示选单、确认服务、服务结束、服务参考与审计闭环；未经授权不对真实营业订单写入。

## 2026-08-27 技师端房间聚合与状态颜色

### 本地完成

- 技师端展示口径调整为 8 个沙发 + 7 个房间；房间内 A/B 床位不再显示为独立区位。
- 底层床位占用、订单和审计不删除；存在顾客选单时映射到其所属房间卡片，服务动作仍使用原占用 ID，保持幂等与审计关联。
- 服务位颜色按状态区分：空闲为中性白灰、待确认（已有顾客下单）为琥珀色、服务中为绿色、已完成为蓝灰色；标签、边框、卡片底色与项目数量同步使用状态色。
- 保持不涉及派单、接单、认领或智慧宝物理资源动作。

### 测试结果

- 后端新增“空闲房间只返回一张卡片”“床位选单映射到父房间”回归测试；技师/画像/权限测试：14 passed。
- 技师端与边界测试：9 passed。
- 管理端完整测试：77 passed；管理端生产构建成功。

### 已发布生产

- 生产 release：`/root/hxy-diy-20260811/releases/technician-room-status-colors-20260827-1`。
- 发布前数据库备份：`/root/hxy-diy-20260811/backups/pre-technician-room-status-colors-20260827-221248.dump`，352 KB，SHA-256 `96be0861e708b17654cda7c0682ba9ae14c563d90b792fe85e82f4527cb6d267`。
- 线上只读验证：`tech-1` 任务接口返回 15 个区位（沙发 8、房间 7）；5 号沙发为 `waiting_service` 且有 4 个顾客下单项目。Manifest、健康接口、迁移 head 与 API 容器状态正常，重启次数为 0。

### 待门店现场验收

- 手机端刷新 `https://diy.hexiaoyue.com/technician/` 后，确认只显示 7 个房间而非 A/B 床位，并确认“待确认”的琥珀色、服务中的绿色与空闲卡片在现场光线下易于区分。

## 2026-08-27 顾客端项目列表价格颜色语义优化

### 本地完成

- 项目列表普通价格使用低饱和品牌绿 `#2f6658`；会员价格使用低饱和草本金 `#8a6a32`；删除线参考价使用灰绿色 `#66736d`。
- 匿名/非会员显示绿色普通价为主、金色会员价为次；会员显示金色会员价为主、灰绿色普通价删除线为次。
- 保持单行价格结构和既有价格计算；未修改详情页、底部选单或结算页。

### 验证结果

- TDD 颜色回归测试先红后绿；顾客端完整测试：113 passed，1 skipped，0 failed。
- 顾客端生产构建成功：Vite 2011 modules transformed。
- Impeccable 检查仅报告既有侧边强调线和宽度动画警告，本轮价格选择器无新增问题。
- Playwright 本地 375px、390px、430px 验证：普通价绿色主价格/金色会员参考价；会员金色主价格/灰绿色删除线普通价；均无溢出、换行或加购按钮遮挡。
- 颜色对比度：普通绿 6.64:1、会员金 5.01:1、参考灰绿 4.96:1。
- 本地预览：`diy-web/output/playwright/project-list-price-color-nonmember-local.png`、`diy-web/output/playwright/project-list-price-color-member-local.png`。

### 发布状态

- 已发布生产：`/root/hxy-diy-20260811/releases/customer-list-price-color-20260827-2`。
- 以服务器实时 `technician-room-status-colors-20260827-1` 为基线，仅替换 `diy-web/dist`；未执行数据库迁移。
- 发布前后完成 Manifest 校验，当前 release Manifest SHA-256：`6c985d1c29d0791940121d3d6e8e4db9853b52a304de443e5e99130680be5e86`。
- API 容器重建后状态 `running`，重启次数 `0`；公网健康接口返回 `status: ok`。
- 公网 H5 返回 200，CSS 已包含 `--price-regular`、`--price-member`；线上 Playwright 390px 验证 12 个项目普通价为绿色、会员参考价为金色，均单行无溢出，“门店价”和“可省”文案数量均为 0。
- 线上预览截图：`diy-web/output/playwright/project-list-price-color-production.png`。

## 2026-08-27 顾客端提交后返回菜单清空选购

### 本地完成

- 修复提交成功页点击“返回项目列表”后仍保留旧选购内容和底部总价的问题。
- 返回菜单时统一清空项目、偏好、加购、目录选择、局部调理和茶饮草稿，并关闭选购抽屉及保存提示。
- 保留已提交服务会话，提交结果、服务状态、评价和到店记录仍可通过“查看清单”访问。
- 会员登录状态下隐藏首页会员卡推荐，会员直接使用会员最低价；非会员仍可看到会员卡推荐。

### 验证结果

- 顾客端完整测试：115 passed，1 skipped，0 failed。
- 顾客端生产构建：成功（Vite 2011 modules transformed）。
- 新增回归测试：空白选购草稿包含项目、偏好、加购、目录选择、局部调理和茶饮全部清空。
- 新增回归测试：会员首页不展示会员卡推荐，非会员仍保留自愿办理入口。

### 发布状态

- 已发布生产：顾客端修复 release 为 `/root/hxy-diy-20260811/releases/customer-return-clear-20260827-1`。
- 发布以服务器实时 `customer-list-price-color-20260827-2` 为基线，仅替换顾客端 `diy-web/dist`；未执行数据库迁移，也未改动管理端或技师端。
- 发布后，其他窗口已将 `current` 切换至 `/root/hxy-diy-20260811/releases/technician-local-care-label-20260827-1`。已逐文件校验当前 release 的顾客端 `index.html`、JS、CSS 与本轮顾客端 release SHA-256 一致，因此本轮修复仍在生产运行版本中。
- 当前 Manifest 校验通过；API 容器运行中、重启次数 `0`；公网健康接口与顾客端入口均返回 `200`。
- 线上匿名顾客端已加载本轮 JS/CSS，项目菜单可正常展示。会员首页不推荐会员卡的条件也已包含在生产版本；本地补充的独立回归测试将在下一次顾客端构建一并纳入。

## 2026-08-27 顾客端项目列表密度与分栏间距优化

### 本地完成

- 项目列表插画从 `84×92px` 收至 `72×80px`，单项最小行高从 `120px` 收至 `108px`，插画保持为品牌识别辅助信息，项目名称、时长、价格和加购动作优先。
- 左侧分类栏与右侧项目列表统一为 `72px` 栅格，消除原 `84px` 栅格与 `72px` 实际导航宽度之间的无效留白；右侧内容左内边距从 `14px` 收至 `8px`。
- 未修改顶部推荐、左侧单字圆圈导航、价格逻辑、加购交互、管理端、技师端或数据库。

### 验证结果

- 新增布局回归测试，覆盖项目图片尺寸、行高、圆角和分栏间距。
- 顾客端完整测试：117 passed，1 skipped，0 failed。
- 顾客端生产构建成功；Impeccable 布局检测未发现新增问题。

### 已发布生产

- 生产 release：`/root/hxy-diy-20260811/releases/customer-menu-gap-20260827-1`。
- 发布前以服务器实时 `customer-menu-density-20260827-1` 为基线，仅替换 `diy-web/dist`；无数据库迁移。
- 发布后 Manifest 校验通过，API 容器运行中、重启次数 `0`，公网健康接口正常；生产入口已加载 `index-qyaFmZA_.js` 与 `index-D23x8l6H.css`。
- 待现场验收：使用未被占用的真实二维码进入项目菜单，确认在实际设备上图片、项目价格与加购按钮的扫读节奏符合门店使用场景。

## 2026-08-27 技师端局部调理部位展示

### 本地完成

- 根因：技师任务接口已透传顾客选单项目的 `diy_preferences`，但移动看板摘要和订单抽屉只渲染 `item.name`，导致“局部调理”未显示顾客选择的具体部位。
- 新增 `technicianOrderItemLabel`：仅在项目 code 为 `hxy-jubu-30` 或名称为“局部调理”时拼接已选择的部位；过滤空值、去重，多部位用“、”分隔；其他项目保持原名称。
- 服务位卡片摘要与订单抽屉明细复用该函数，避免两个入口显示不一致。

### 涉及文件

- `C:\Users\gaoji\WorkBuddy\2026-07-31-12-31-02\admin-react\src\technician\technicianMobile.ts`
- `C:\Users\gaoji\WorkBuddy\2026-07-31-12-31-02\admin-react\src\technician\TechnicianTodayPage.tsx`
- `C:\Users\gaoji\WorkBuddy\2026-07-31-12-31-02\admin-react\tests\technician-mobile.test.ts`

### 测试结果

- TDD：新增“局部调理在订单明细中展示顾客选择的具体部位”测试先因缺少 helper 导出失败，完成实现后通过。
- 技师端与边界：`node --experimental-strip-types --test tests/technician-mobile.test.ts tests/navigation-boundary.test.ts`，10 passed。
- 管理端完整测试：`npm test`，78 passed。
- 后端技师、顾客服务参考与权限：`python -m pytest tests/test_technician_portal_api.py tests/test_customer_profile_records_api.py tests/test_auth_boundary_p0.py -q`，14 passed（1 条既有依赖弃用警告）。
- 管理端生产构建：`npm run build` 成功；仅有既有单 bundle 大于 500 KB 提示。

### 已发布生产

- 发布基线：服务器实际 `current` 为 `/root/hxy-diy-20260811/releases/customer-list-price-color-20260827-2`。
- 生产 release：`/root/hxy-diy-20260811/releases/technician-local-care-label-20260827-1`；仅替换 `admin-react/dist`，保留后端、顾客端和数据库 schema 的线上版本；未执行数据库迁移。
- 发布前数据库备份：`/root/hxy-diy-20260811/backups/pre-technician-local-care-label-20260827-224957.dump`，352 KB，SHA-256 `80887c999b6200a14dd50734384c2f47d0f989caf51d00da08dcf3d3c68308c4`。
- 新 release Manifest 全量校验通过，Manifest SHA-256：`a269e8f8501ff91420e05785d5c11ead08a249b97405174d4ac5cf27354ebe86`；原子切换后 API 容器重建，重启次数 0。
- 公网验证：`/api/v1/health` 返回 200；`/technician/` 返回新构建入口。在 390px 手机视口的只读核验中，4、5 号沙发摘要及 5 号沙发订单抽屉均显示具体部位，例如“局部调理（肩颈）”“局部调理（腿部）”；浏览器控制台无错误。

### 待门店现场验收

- 用新的顾客测试选单继续验证“顾客提交 → 技师端服务位摘要与抽屉均显示具体部位”。
- 未经门店明确授权，不对真实营业订单执行确认服务、服务结束或顾客服务参考写入。

## 2026-08-27 技师端局部项目短文案

### 本地完成

- 按产品口径将技师端局部项目从“局部调理（肩颈）”收紧为“局部：肩颈”，便于手机服务位卡片和订单抽屉快速扫读。
- 同一项目选择多个部位时展示为“局部：腰臀、腹部”；非局部项目保持原名称。
- 卡片摘要与订单抽屉继续共用 `technicianOrderItemLabel`，不改订单数据、服务状态或业务动作。

### 涉及文件

- `C:\Users\gaoji\WorkBuddy\2026-07-31-12-31-02\admin-react\src\technician\technicianMobile.ts`
- `C:\Users\gaoji\WorkBuddy\2026-07-31-12-31-02\admin-react\tests\technician-mobile.test.ts`

### 测试结果

- TDD：新格式测试先失败（实际为“局部调理（肩颈）”），最小实现后通过。
- 技师端与边界：10 passed。
- 管理端完整测试：78 passed。
- 后端技师、顾客服务参考与权限：14 passed（1 条既有依赖弃用警告）。
- 管理端生产构建：成功；仅有既有单 bundle 大于 500 KB 提示。

### 已发布生产

- 发布基线：`/root/hxy-diy-20260811/releases/technician-local-care-label-20260827-1`。
- 生产 release：`/root/hxy-diy-20260811/releases/technician-local-short-label-20260827-1`；仅更新 `admin-react/dist`，未执行数据库迁移。
- 最终生产 `current`：并发顾客端发布后切换为 `/root/hxy-diy-20260811/releases/customer-menu-density-20260827-1`；已复核其 `admin-react/dist/index.html` 仍引用本轮 `index-Br0uHx01.js`，因此技师端短文案仍在当前线上版本中生效。
- 发布前数据库备份：`/root/hxy-diy-20260811/backups/pre-technician-local-short-label-20260827-231704.dump`，353 KB，SHA-256 `5b12bd54e71af1ce53a36e4a788b717b465a8565f9c3c04c2f4511a461c4b041`。
- Manifest 全量校验通过，Manifest SHA-256：`f7d48d14f816d1e0a5b404cf2b5a81c2e806a750de6189f432c458aa3eb82ba2`；API 容器重建后重启次数为 0。
- 公网 390px 技师端只读验证：4、5 号沙发摘要及 5 号沙发订单抽屉显示“局部：腰臀”“局部：肩颈”“局部：腿部”，浏览器控制台无错误；未触发服务状态写入。

### 待门店现场验收

- 在现场手机和新提交的测试选单上确认短文案在卡片与订单抽屉内均便于扫读。

## 2026-08-28 顾客端提交后返回菜单与刷新恢复修复

### 本地完成

- 根因确认：提交成功页的“返回项目列表”此前只清空 React 内存草稿；本地 `EntryRecord` 仍保存已提交项目，刷新时初始化逻辑又调用 `hydrateSelection` 将旧项目回填到底部选购栏。
- 同时修正状态规则：`submitted + waiting_service` 不再被当作可编辑选单；只有前台确认且服务中的会话可以继续加选。
- `EntryRecord` 增加 `draftClearedAfterSubmit`。顾客从成功页返回列表时，内存与本地记录同步清空；刷新仍保留只读服务会话、清单、服务状态、评价与到店记录，但不会恢复旧选购草稿。
- 提交成功页的左边缘右滑和“返回项目列表”按钮统一调用同一返回动作；有打开的反馈等弹层时，边缘滑动仍优先关闭弹层，不会误返回菜单。

### 验证结果

- TDD：新增“返回菜单后刷新不恢复草稿”“未返回菜单仍可恢复已提交清单”“服务中允许加选”“成功页无弹层左滑返回菜单”回归测试；缺少实现和旧状态规则时均已先失败，再完成最小修复。
- 顾客端完整测试：`npm test`，121 passed、1 skipped、0 failed。
- 顾客端生产构建：`npm run build` 成功，Vite 转换 2012 个模块。
- 公网冒烟：启用 `HXY_PRODUCTION_SMOKE=1` 后 121 passed、0 skipped、0 failed；入口、静态资源与 `/api/v1/health` 均返回正常。

### 已发布生产

- 生产 release：`/root/hxy-diy-20260811/releases/customer-submitted-return-20260827-1`。
- 发布基线：服务器实际 `customer-menu-gap-20260827-1`；仅替换 `diy-web/dist`，不改管理端、技师端、后端代码或数据库，未执行迁移。
- 原子切换后重建 `hxy-diy-api`；`current` 已指向本 release，Manifest 校验通过，SHA-256 为 `ee5c5f2f2690cce2676e7aecad0e371c1f2506f67847dcd625f99089a02ec664`。
- API 容器状态 `running`、重启次数 `0`；公网顾客端入口与健康接口均返回 `200`，线上入口加载 `index-DIVQ2MbX.js`，包含本轮草稿清空标记。

### 待现场验收

- 使用门店授权的测试服务位和会员账号走一次“选购提交 → 成功页左边缘右滑返回项目列表 → 刷新页面”，确认底部选购栏为空，同时“查看清单”、服务状态和评价入口仍可用。
- 不要用真实营业订单做该写入流程回归；自动化和静态冒烟不替代门店现场验收。

## 2026-08-28 全授权验收收口（顾客端）

### 本地完成

- 顾客端生产冒烟：`HXY_PRODUCTION_SMOKE=1 npm test`，`135 passed / 0 failed`。
- 顾客端生产构建：`npm run build` 成功，Vite 转换 2013 个模块。
- 后端顾客链路关键回归：选单、价格、会员、服务状态、评价、服务位释放与技师确认相关用例 `135 passed`（1 条既有 httpx/Starlette 弃用警告）。
- 后端全量基线：`490 passed / 19 failed / 7 skipped`。19 个失败复核为后台旧角色迁移契约、已废止的 DIY 物理资源接口状态码、运营统计历史断言和 Alembic head 名称不一致；未发现顾客端选购、会员价格、提交追加、服务状态同步链路失败。
- 生产只读移动端（iPhone 15 视口）验证：可用服务位进入成功，分类与右侧项目列表正常，12 个项目与详情图正常渲染；当前详情价格只显示本项目，底部选购栏与详情价格语义分离；控制台无新增错误。已结束服务位返回 409 保护页属于业务状态，不是白屏。
- 生产菜单合同核对：`GET /api/v1/projects?store_id=1` 返回 12 项，门店价/团购价/会员价与 2026-08-28 菜单表逐项一致。

### 已发布生产

- 顾客端静态 overlay 首次发布至 `/root/hxy-diy-20260811/releases/customer-append-flow-20260828-1`；随后被并行的 `technician-account-lifecycle-20260828-1` release 作为最新基线保留，当前线上顾客端仍加载同一 `index-sKYOcMXN.js`。仅替换 `diy-web/dist`，未执行数据库迁移。
- 发布前数据库备份：`/root/hxy-diy-20260811/backups/pre-customer-append-20260828-073122.dump`，363 KB，SHA-256 `86cf3bcb9f2699ca7f15c61912cd2b15c877c033aefa42d29188ec209f2c3f1f`。
- `current` 原子切换后，按生产 `.env` 重建 `hxy-diy-api`；期间首次未显式传入 env 导致临时重启，已立即使用线上 `.env` 恢复，最终 API/数据库均 `running`、重启次数 `0`，未执行数据库迁移。
- 首次 overlay Manifest SHA-256：`3f3c9ad7acb0e2b9c040ba16045657f98e70dc0ac5da07740452ec15e0120745`；当前线上最新 release `technician-account-lifecycle-20260828-1` Manifest SHA-256：`44cc614662106b63c10dbc831cbad5bcb0805a15577355379b68de62b1bcd545`，服务器 `sha256sum -c MANIFEST.sha256` 通过。
- 公网发布后核验：H5 入口 200 并加载 `index-sKYOcMXN.js`，`/api/v1/health` 200，`/api/v1/projects?store_id=1` 返回 12 项。

### 待现场验收

- 会员真实短信登录和登录后最低价展示仍需门店授权测试手机号及验证码；不能用自动化账号替代真实短信链路。
- 多设备并发抢位、断网恢复跨设备同步、超时释放现场观察、技师画像填写及智慧宝开位/派钟并行，仍需在不影响营业的授权服务位完成 L4 验收。
- 后端全量 19 个失败属于后台/迁移边界，本顾客端窗口不修改其权限策略；生产可用声明需待后台负责人完成角色迁移契约与 Alembic merge 后重新跑全量。

## 2026-08-28 顾客端会员总价恢复修复发布

### 本地完成

- 修复已提交会话恢复时错误读取旧快照顶层 `member_total_cents` 单项目金额的问题；无促销时优先使用会员小计或明细行汇总，有促销时保留服务端最终减免总价。
- 顾客端测试：`npm test` 通过；生产构建：`npm run build` 通过。

### 已发布生产

- 新 release：`/root/hxy-diy-20260811/releases/customer-member-total-20260828-1`。
- 仅替换 `diy-web/dist`，未修改后端、管理后台、技师端或数据库，未执行迁移。
- 原子切换后 `current` 指向该 release，Manifest 全量校验通过；线上入口、`/api/v1/health`、项目列表接口均返回 200。
- 线上入口当前加载顾客端构建 `index-DKKrtuyW.js`。

### 待现场验收

- 使用门店授权测试选单复核提交恢复场景：门店价合计、会员价合计和可省金额应与明细一致，不再出现单项目会员价。
- 会员真实短信登录、多设备并发、断网恢复、超时释放和技师画像仍需独立现场验收。

## 2026-08-28 顾客端二维码服务位优先级修复发布

### 本地完成

- 根因：地图刷新和会话恢复路径无条件使用服务端 `is_current`，旧会话标记可能覆盖二维码 URL 的明确服务位。
- 新增 `resolveRequestedPosition`：存在 URL/已绑定编码时按编码取位；只有无编码入口才按 `is_current` 回退。
- 新增二维码串位回归测试；顾客端完整测试 `133 passed / 1 skipped / 0 failed`，生产构建成功。

### 已发布生产

- 新 release：`/root/hxy-diy-20260811/releases/customer-seat-binding-20260828-1`。
- 仅替换 `diy-web/dist`，未修改后端、管理后台、技师端或数据库，未执行迁移。
- 原子切换后 `current` 指向该 release，Manifest 校验通过；线上入口加载 `index-sKYOcMXN.js`，健康接口和项目列表接口均返回 200。
- 发布前发现并修复了复制符号链接会破坏旧 release Manifest 的风险；旧线上 release 已恢复并重新校验通过。

### 待现场验收

- 使用两个已授权服务位二维码同时打开手机，确认 URL 服务位、刷新、返回和再次打开均不串位。
- 继续验收会员真实短信、并发抢位、断网恢复和服务位生命周期；自动化验证不替代真实门店授权验收。

## 2026-08-28 顾客端优惠文案与二维码冲突保护发布

### 本地完成

- 详情页和登录弹层将优惠券说明统一为“登录后领取，优惠以门店结算为准”，删除“满足条件自动抵扣”等不符合线下结算事实的承诺。
- 修复明确二维码服务位在浏览器已有其他服务位会话时被错误恢复到旧服务位的问题：只有无明确服务位的普通入口才允许恢复当前会话。
- 新增二维码冲突回归测试；顾客端测试 `135 passed / 1 skipped / 0 failed`，生产构建成功，入口为 `index-Dbadxy5R.js`。

### 已发布生产

- 生产 release：`/root/hxy-diy-20260811/releases/customer-seat-binding-qr-conflict-20260828-1`。
- 以 `customer-copy-coupon-settlement-20260828-1` 为基线，仅替换 `diy-web/dist`；未修改后端、管理后台、技师端或数据库，未执行迁移。
- 发布前数据库备份：`/root/hxy-diy-20260811/backups/pre-customer-copy-coupon-settlement-20260828-1735.dump`，376277 bytes，SHA-256 `713a298ab2cb929a3a1280ae1bd2991d0c5fa820050607d47f1706ca485cda71`。
- Manifest 全量校验通过；API 容器已按新 release 重建，公网 H5 加载 `index-Dbadxy5R.js`，健康接口 200，项目列表返回 12 项。

### 体验结论

- 顾客端菜单、分类、12 个项目、会员参考价和服务位标题在 390px 移动视口可正常渲染；服务位 5 号与 6 号的生产地图数据独立且无串位标记。
- 当前不再把优惠券描述为自动抵扣；会员价展示仍遵循会员最低价、不领券原则。
- 本次浏览器只读检查未提交生产选单、未发送短信、未修改服务位状态。

### 待现场验收

- 使用门店授权的 5 号、6 号二维码在两台设备同时扫码，确认 URL、刷新、返回及再次打开均保持各自服务位；不得使用真实营业订单。
- 使用授权会员手机号完成真实短信登录，核对会员价切换、已提交清单和刷新恢复；非会员再核对优惠券领取文案。
- 多设备并发、断网恢复、技师确认服务后状态同步、超时释放和画像记录仍需门店现场完成；自动化与只读线上检查不能替代营业验收。
# 2026-08-28 顾客端手动换位后服务位状态保持修复

## 本地完成

- 根因：顾客从二维码入口手动选择其他空闲服务位后，地图刷新仍优先使用组件挂载时读取的旧 URL `seat` 参数；保存选单时会把当前服务位覆盖回旧位置。
- 新增 `resolveActivePositionCode`，地图刷新与顾客服务状态轮询优先使用当前状态中的服务位编码，首次进入仍保留二维码编码约束。
- 新增回归测试：手动从 5 号换到 7 号后，当前编码优先且不会被初始二维码编码覆盖。

## 验证结果

- 顾客端测试：`npm test`，`136 passed / 0 failed / 1 skipped`。
- 顾客端生产构建：`npm run build` 成功，构建产物 `index-DebsI3ec.js`。
- 无痕浏览器只读验证：清除 Playwright 会话后，二维码入口正确显示服务位；旧会话残留场景已定位并在本地修复，待发布后重新执行写入流程验证。

## 已发布生产

- 待发布：本轮修复尚未切换生产 release。

## 待验收

- 发布后使用清空缓存的新浏览器，在授权服务位完成“扫码/选位 -> 配置 -> 加入 -> 刷新地图”并确认服务位、选单和价格不串位。
- 会员短信登录、技师确认/结束、并发、断网恢复、超时释放和画像记录仍需门店授权现场验收。
# 2026-08-28 沙发占用不释放根因修复

## 本地完成

- 根因：历史服务占用（1、2、3 号沙发）缺失 `expected_end_at`，释放策略此前直接排除 `in_service`/`post_service_present`，导致占用长期不进入自动释放候选；生产调度器本身正在每分钟运行，`held`/`waiting_service` 自动释放审计持续产生。
- 修复：新增服务超时兼容截止时间。优先使用 `expected_end_at`，缺失时使用 `actual_service_end_at`，再缺失时使用 `actual_start_at + 60 分钟`；统一再增加 30 分钟宽限。三类时间锚点都缺失时继续保守跳过，避免误释放。
- 生产只读复核：1、2、3 号沙发的兼容截止时间均已超过当前时间；7、8 号按现有预计结束时间尚未到自动释放截止点；6 号为仍在有效期内的临时占位。

## 涉及文件

- `hxy-server/app/domain/occupancy_release_policy.py`
- `hxy-server/tests/test_occupancy_release_policy.py`

## 测试结果

- 后端服务位释放、调度器、服务状态专项：`53 passed`。
- 管理端测试：`88 passed`。
- 管理端生产构建：成功，`3153 modules transformed`；仅有既有单 bundle 大小警告。
- 后端全量仍存在既有角色迁移、废止接口状态码、历史统计断言和 Alembic 多 head 失败，未作为本轮发布依据。

## 发布状态

- 已发布生产：发布 release `occupancy-release-20260828-1` 完成原子切换并重建 API；随后服务器另一并行发布流程将 `current` 原子切换到 `technician-profile-entity-20260828-2`，该 release 已确认保留本次 `occupancy_release_policy.py` 修复（SHA-256 `802b5388b0343ed05a3ebf54f4f7b391623a3611bbb3827b3193fd6fc5e93e17`）。
- 发布前数据库备份：`/root/hxy-diy-20260811/backups/pre-occupancy-release-20260828-130059.dump`，SHA-256 `be44262a659b0c693dd86d3cb8c2e2e7675324e6e90d011372060da673fdc6f1`。
- API 容器重建后运行正常，公网 `/api/v1/health` 返回 `status: ok`；未执行数据库迁移。
- 调度器自然执行后，1、2、3 号沙发均变为 `released`，审计记录 `occupancy_auto_released`，原因 `service_end_grace_expired`；未人工修改生产占用数据。
- 当前生产 release 以服务器实际 `readlink` 为准：`technician-profile-entity-20260828-2`。

## 待现场验收/后续

- 需由生产发布流程发布本修复后，使用门店授权测试服务位验证历史兼容释放、技师确认服务、服务结束和审计记录。
- 1、2、3 号历史占用已自动释放；仍需门店确认现场看板恢复可选状态。后续类似缺失时间锚点的数据继续由店长按业务流程核实，不应直接手工删除。
# 2026-08-28 技师画像实体关联修复

## 本地完成

- 定位根因：画像接口原按服务分配记录匹配技师，生产测试订单由技师直接确认/结束服务时不存在该分配记录，导致 403。
- 新增回归测试，先验证旧逻辑返回 403，再改为按 `technician_finish_service` 审计的 `entity_id=position_occupancy.id` 关联，并保留门店、技师、动作约束。
- 技师移动端今日页改用 `/technician/tasks`，保留 `user_id`、`selection_session_id`、`occupancy_id`；仅本人完成服务后显示“填写服务参考”。画像表单支持年龄段、性别、体型、职业、标签和备注，提交严格走结构化画像接口。
- 后端画像/技师专项：13 passed；管理端测试：88 passed；管理端生产构建成功（仅既有 bundle 体积警告）。

## 已发布生产

- 生产 release：`technician-profile-entity-20260828-2`，以服务器最新 `occupancy-release-20260828-1` 为基线，仅替换 `admin_v2.py` 与 `admin-react/dist`，未执行数据库迁移。
- 发布前数据库备份：`/root/hxy-diy-20260811/backups/pre-technician-profile-entity-20260828-130028.dump`，SHA-256：`de557aec6e9eda8fb3c70d513d5fbd40fd1e5c52b061a8288f755257f23192a1`。
- Manifest 校验通过；API 重建后容器运行正常，公网 `/api/v1/health` 返回 200，管理端入口返回 200。
- 使用授权账号 `tech-1` 在 8 号沙发已结束测试会话上成功写入画像（年龄段、性别、体型、职业、标签、备注），接口返回 200，证明实体关联权限已生效。

## 待现场验收

- 使用门店授权测试服务位和技师手机完成一次“顾客提交 → 技师确认服务 → 服务结束 → 填写服务参考 → 管理端查询”现场闭环。
- 多设备并发、断网恢复、超时释放和智慧宝并行操作仍需现场授权验收；本次生产验证未触碰真实营业订单。

## 2026-08-28 生产授权闭环与并发验收

### 已发布生产

- 公网健康接口返回 `status: ok`；服务位地图 8 个沙发均可读取；项目接口返回 13 个项目。
- 使用全新匿名会话在 7 号沙发完成：顾客提交草本泡脚 → 技师 `tech-1` 确认服务 → 顾客端状态同步为 `in_service` → 技师结束服务 → 状态变为 `post_service_present`。
- 技师画像按当前接口合同成功写入并查询：测试顾客画像记录 ID 4，管理端查询返回 1 条；记录带有“仅作到店服务参考，不构成医疗建议”免责声明。
- 两次独立请求抢占已占用 8 号沙发均返回 `409 POSITION_OCCUPIED`，未发生串单。
- 5 号、6 号沙发可被两个独立入口分别占用（测试占用 ID 301、302），服务位绑定独立。
- 移动端无痕 Playwright 只读检查：分类、项目价格、详情页和底部选购栏正常；未登录状态显示门店价与会员参考价，项目详情不显示整单总价。

### 现场验收边界

- 本轮使用生产授权测试服务位，不涉及真实营业订单；7 号测试占用已结束但仍处于 `post_service_present`，由门店按智慧宝流程确认离位/清洁。
- 5、6 号为并发边界测试产生的临时占用，待调度器按超时策略自动处理或由门店授权回收。
- 断网恢复已在顾客端自动化无痕会话验证；跨设备断网同步、真实会员短信、超时现场观察及智慧宝并行操作仍需门店手机现场验收，不能以自动化结果替代。

## 2026-08-28 养生小项固定项目文案修复

- 顾客端将养生小项（采耳、拔罐、刮痧、头疗、足部精修）从“可自由搭配”改为“固定项目”。
- 保留小项独立加入本次服务的能力，不影响局部调理的按部位多选逻辑，也不改变价格。
- 新增回归测试；顾客端测试 `137 passed / 1 skipped`，生产构建成功。
- 已发布生产：`customer-small-fixed-20260828-1`。仅替换顾客端静态资源，Manifest 校验通过，使用生产专用 Compose 重建 API 容器（未执行数据库迁移）。
- 线上复核通过：养生小项卡片显示“固定项目”，其他可配置主项目仍显示“可自由搭配”；健康接口返回 200。

## 2026-08-28 顾客端服务词汇优化

- 分类名称改为“更多服务”；顾客端移除“小项”“固定项目”“可自由搭配”“按次”等内部或计费术语。
- 拔罐、刮痧、足部精修显示“单次服务”；采耳和头疗只显示服务时长；局部推拿显示“按部位选择”。
- 生产 release：`customer-service-copy-20260828-1`，仅替换顾客端静态资源，Manifest 校验通过并重建 API 容器，未执行数据库迁移。
- 线上无痕移动端复核通过：分类显示“更多服务”，单次项目显示“单次服务”，页面不再出现旧术语；健康接口正常。
- 生产超时观察：5 号沙发授权测试占用在保持期限到达后由调度器自然回收，服务位地图恢复为 `available`；未执行人工释放。
- 后端服务位释放、技师任务和顾客画像专项：`22 passed`；仅有既有 httpx/Starlette 弃用警告。
# 2026-08-29 顾客端 Impeccable 审查与无障碍/价格加固

## 本地完成

- 按 `impeccable critique + audit` 完成顾客端移动端审查；设计评分 24/40，技术审计 13/20。
- 修复服务位伪按钮与项目卡片的 Enter/Space 键盘激活，项目卡补 `role=button`、`tabIndex`，加购按钮补 `aria-pressed`。
- 顾客端列表/推荐/茶饮选项及详情模块图片补 `loading="lazy"`、`decoding="async"`。
- 修复非会员详情页将更低会员价错误划线的问题：非会员显示绿色门店价与金色会员价参考，会员态才划线门店价；详情底部价格颜色随身份区分。
- 顾客端过滤“可自由搭配”“可按需加选”“利润款”等内部标签，茶饮副标题不再显示“按需要，自由搭配”，统一为“到店先一杯”。默认服务徽标改为“可加选服务”。
- 顾客端测试：`144 passed / 0 failed / 1 skipped`；生产构建成功，入口 `index-TMX31x-u.js`。
- Impeccable detector 仍报告 8 条 warning：7 条为有意品牌强调条纹误报，1 条为进度条 `transition: width`，本轮未改动。

## 已发布生产

- 新 release：`/root/hxy-diy-20260811/releases/customer-audit-20260829-2`。
- 仅替换 `diy-web/dist`，未修改后端、管理端或数据库，Manifest 校验通过，API 容器按新 release 重建。
- 线上健康接口返回 `status: ok`；无痕移动端确认新入口加载，茶饮副标题为“到店先一杯”，项目卡键盘语义生效，局部推拿按钮名称一致，默认徽标为“可加选服务”。

## 待现场验收

- 真实会员短信、双设备并发、断网恢复、超时释放、技师确认/结束与画像查询仍需门店授权手机现场走通；本轮未触碰真实营业订单。
- 低对比度辅助文字和 30–38px 图标触控热区仍是后续 P1/P2 加固项；顶部 6 张促销卡的首屏负担也待产品决定是否压缩。

# 2026-08-29 顾客端无障碍与对比度加固

## 本地完成

- 详情页普通偏好、目录选项、局部服务和茶饮按钮统一补充 `aria-pressed`，辅助技术可读取当前选中状态。
- 优惠提示卡增加键盘 Enter/Space 操作语义；详情返回按钮触控区提升至 44px。
- 顾客端选单、项目详情和茶饮辅助文字统一使用 `--muted` / `--price-reference`，提高浅色背景下的可读性。
- 移除未使用促销进度条的 `transition: width` 布局动画，避免宽度动画引起布局抖动。
- 顾客端测试：`145 passed / 0 failed / 1 skipped`；生产构建成功，入口 `index-BZfPGsxN.js`。
- Impeccable detector 剩余 7 条品牌强调条纹 warning，均为既有有意样式；不再报告布局属性动画。

## 已发布生产

- 新 release：`/root/hxy-diy-20260811/releases/customer-a11y-20260829-1`，仅替换顾客端 `diy-web/dist`。
- Manifest 校验通过，`current` 已原子切换；API/数据库容器重建后保持运行，健康接口返回 `status: ok`。
- 无痕移动端复核通过：3 号沙发绑定正确，入口非空白，控制台无错误；详情返回按钮为约 44×44px，详情选项存在 `aria-pressed`，图片懒加载生效。

## 待现场验收

- 真实会员短信、双设备并发、断网恢复、超时释放、技师确认/结束与画像查询仍需门店授权手机现场走通。

# 2026-08-29 顾客端页面轻动效收口

## 本地完成

- 新增详情页、选项反馈、底部清单和 Toast 的轻动效预设，仅使用透明度、位移和缩放，不动画宽高等布局属性。
- 项目详情、茶饮详情、局部服务详情统一增加详情层动效标记；底部待提交选购栏增加轻推入/淡入反馈。
- 选购清单标题根据状态明确显示“本次待提交”或“已提交服务”，预计合计保留 `aria-live="polite"` 播报。
- 增加触控按钮短暂缩放与颜色过渡，并保留 `prefers-reduced-motion: reduce` 降级规则。
- 顾客端全量测试：`149 passed / 0 failed / 1 skipped`。
- 顾客端生产构建成功：Vite 转换 `2013` 个模块，主 bundle 约 `416.56 kB`（gzip `129.54 kB`）。

## 已发布生产

- 否。本轮仅完成顾客端本地源码、测试和构建，未修改服务器或生产 `current`。

## 待现场验收

- 需在无痕移动端复核详情进入/返回、底部清单出现/关闭、提交后草稿清空和刷新不恢复旧草稿。
- 真实会员短信、双设备并发、断网恢复、超时释放、技师确认/结束与画像查询仍需门店授权手机现场走通。
# 2026-08-29 管理后台 ProComponents/Refine 渐进接入第一阶段

## 本地完成

- 按“保留 React/Vite + Ant Design，采用 Ant Design Pro 信息架构和 ProComponents，Refine 渐进接管数据访问与 CRUD”方向推进。
- 新增统一导航注册表和 Refine 数据访问适配层；保留现有门店绑定、缓存、登录失效和错误归一化逻辑。
- 首个低风险页面“门店主数据”改用 `PageContainer`、`ProTable`、`ModalForm`、`ProForm*`，列表/创建/编辑统一经 Refine provider 访问 `admin/v2/stores`。
- 修复后端门店主数据权限根因：仅允许 `role=admin` 且未绑定具体门店的总部管理员维护；店长、普通员工和技师继续禁止访问。
- Refine 列表适配同时兼容后端 `items/total` 与标准 `data/total` 分页响应。
- 技师画像写入 API 显式补充 `source` 类型，保留幂等请求头；同步更新过时的前端契约测试。

## 涉及文件

- 管理端：`admin-react/src/pages/StoresPage.tsx`、`admin-react/src/pages/stores-page-model.ts`、`admin-react/src/core/dataProvider/refine.ts`、`admin-react/src/api.ts`、`admin-react/src/technician/TechnicianProfileSheet.tsx`
- 管理端测试：`admin-react/tests/stores-page-model.test.ts`、`admin-react/tests/refine-provider.test.ts`、`admin-react/tests/technician-workspace.test.ts`
- 后端：`hxy-server/app/api/admin_v2.py`

## 测试结果

- 管理端全量测试：`98 passed / 0 failed`。
- 后端门店主数据与门店隔离专项：`3 passed / 0 failed`（总部管理员维护、绑定门店管理员拒绝、门店员工仅访问本店房间）。
- 管理端生产构建：成功，Vite 转换 `3997` 个模块；主 bundle 约 `2.26 MB`，仍有大于 500KB 的拆包警告，后续按路由懒加载处理。
- 依赖安装遗留 `7` 个 npm audit 漏洞（2 moderate、5 high），本轮未执行自动升级。

## 发布状态

- 已发布生产：否。本轮仅本地完成，未修改服务器、数据库或生产 `current`。
- 待现场验收：门店主数据页面需使用总部管理员账号完成只读、创建、编辑和权限边界验收；不得用店长账号替代。

## 尚未完成事项

- 继续按低风险顺序迁移 `ProductsPage`、`TechsPage`、`ProjectsPage`，暂不先改服务位状态机页面。
- 进行管理端按路由拆包，降低首屏 bundle 体积。
- 完成真实浏览器页面验证后，再评估是否进入发布门禁；发布前仍需数据库备份、Manifest 校验、线上健康检查和现场授权验收。

# 2026-08-29 管理后台商品管理渐进迁移

## 本地完成

- 商品管理页改用 `PageContainer`、`ProTable`、`ModalForm` 和 `ProForm*`，列表读取与新建统一通过 Refine data provider。
- 增加商品资源键、商品类型/金额模型；商品列表兼容数组和分页响应，分类与状态筛选在现有接口响应上稳定生效。
- 商品创建强制使用当前登录员工绑定的门店；总部账号未绑定门店时显示明确提示，不发起越权请求。
- 管理端测试：`100 passed / 0 failed`；生产构建成功，Vite 转换 `3998` 个模块，主 bundle 约 `2.27 MB`，保留既有拆包警告。

## 发布状态

- 已发布生产：否。本轮仅本地完成，未修改服务器、数据库或生产 `current`。
- 待现场验收：使用绑定门店的管理员或店长账号验证商品列表、分类/状态筛选和新建商品；总部管理员需先完成门店绑定或门店切换流程。

## 尚未完成事项

- 商品编辑、上下架和图片上传仍沿用现有后端契约，待确认 PATCH/POST 兼容策略后再迁移。
- 下一阶段继续迁移技师管理和服务项目管理，并按路由拆包降低首屏体积。

# 2026-08-29 顾客端轻动效构建与浏览器冒烟复核

## 本地完成

- 顾客端全量测试：`149 passed / 0 failed / 1 skipped`。
- 顾客端生产构建成功：Vite 转换 `2013` 个模块，主 bundle `416.65 kB`（gzip `129.56 kB`）。
- 详情页、底部选购栏、选购清单和 Toast 的动效仅使用透明度、位移和短暂缩放，不改变布局尺寸；保留减少动效降级规则。

## 浏览器冒烟复核

- 使用新建浏览器标签打开 `https://diy.hexiaoyue.com/?store=1&seat=sofa-03`，未使用已有登录态或敏感凭据。
- 页面非空，标题为“荷小悦 · 到店选项目”，服务位正确显示为 3 号沙发。
- 项目详情可打开，详情底部显示当前项目价格；加入后返回项目列表，底部显示整单“预计合计”和“提交给前台”，两者价格上下文保持区分。
- 浏览器控制台未发现 error/warn；移动端截图确认主列表与详情层无明显重叠或布局抖动。

## 发布状态

- 已发布生产：否。本轮只完成顾客端源码、测试、构建和线上只读冒烟，未切换服务器 `current`。

## 待现场验收

- 仍需门店授权手机完成真实会员短信、双设备并发、断网恢复、超时释放、技师确认/结束与画像查询。
- 提交给前台后的真实订单状态同步，以及智慧宝并行开沙发/释放流程，不能由本地自动化冒烟替代。

# 2026-08-29 管理后台技师管理渐进迁移

## 本地完成

- 技师管理页改用 `PageContainer`、`ProTable`、`ModalForm` 和 `ProForm*`，列表读取、分页、业务状态/登录状态筛选统一经 Refine data provider。
- 保留技师账号开通、重置登录、停用、恢复、离职、返聘等既有生命周期接口、确认文案、一次性凭证展示和幂等请求行为。
- 新增技师资源键；建档时强制使用当前登录员工绑定的门店，未改变后端角色和门店隔离规则。
- 管理端测试：`100 passed / 0 failed`；生产构建成功，Vite 转换 `3998` 个模块，主 bundle 约 `2.27 MB`，仍有既有拆包警告。

## 发布状态

- 已发布生产：否。本轮仅本地完成，未修改服务器、数据库或生产 `current`。
- 待现场验收：使用店长账号验证技师列表分页/筛选、建档、开通登录及凭证交接；用普通员工和技师账号确认无写操作入口。

## 尚未完成事项

- 商品编辑、上下架和图片上传仍待后端契约确认；服务项目管理仍保留旧页面，下一阶段迁移。
- 继续按路由拆包降低首屏体积；发布前仍需数据库备份、Manifest 校验、线上健康检查和现场授权验收。

# 2026-08-29 管理后台授权验收（本地）

## 本地完成

- 本地 Vite 管理端启动成功：`http://127.0.0.1:5174/admin/`（5173 已被占用，自动切换端口）。登录页标题、账号/密码表单和登录按钮渲染正常。
- 使用本地模拟店长会话检查信息架构：侧栏显示今日运营、服务与商品、人员与顾客、门店与资源、营销、系统分组；商品和技师入口均可见。
- 使用本地模拟普通员工会话访问 `/products`：前端重定向至 `#/forbidden`，菜单隐藏商品、项目、营销等管理入口，仅保留门店日常运营、技师和房间资源。
- 使用本地模拟技师会话从管理端入口访问：前端按设计跳转至 `/technician/today`。

## 验收限制

- 本地仅启动了管理端 Vite，未启动 FastAPI，因此店长页面的列表请求显示 API 500；这不能替代真实接口验收。
- Vite 开发服务器直接请求 `/technician/today` 返回 404，属于嵌套路由回退限制；生产环境需由 FastAPI 静态挂载和真实部署配置复核。
- 未使用或输出任何生产账号、密码、令牌；未执行创建商品、创建技师或账号生命周期写操作。

## 发布状态

- 已发布生产：否。本轮仅本地授权验收，未修改服务器、数据库或生产 `current`。
- 待现场验收：使用门店授权店长账号连接真实 API 验证商品/技师列表、筛选、创建和账号生命周期；使用普通员工、技师真实账号验证菜单与路由边界，并确认 `/technician/today` 生产回退正常。

# 2026-08-29 技师服务参考快记发布

## 本地完成

- 技师服务结束后的顾客参考快记 PRD、后端幂等与权限契约、手机端首屏表单和专项测试已完成。
- 后端专项测试：`21 passed / 0 failed / 1 warning`；前端技师相关测试：`14 passed / 0 failed`；管理端生产构建成功（Vite `3997` 模块）。
- 新迁移 `20260829_tech_profile_note` 已通过 release 构建、路由导入和 Manifest 校验。

## 已发布生产

- 已发布 release：`technician-profile-quick-note-20260829-1`。
- 生产 `current` 已原子切换至该 release，API 镜像已重建并运行。
- 已补齐 release 运维脚本执行权限，Manifest 内容校验仍通过。
- 数据库发布前备份：`/root/hxy-diy-20260811/backups/pre-technician-profile-quick-note-20260829-151714.dump`。
- 备份 SHA-256：`3512b250c9c29b897d7cd5fb43faad7a11d94ae08472be958a50005131973c42`。
- release Manifest SHA-256：`e040d4941f93603bbb22cdc8d888e2ae4e0c499f283bd4e8b584ad08dd7c9949`。
- 线上数据库 head：`20260829_tech_profile_note`；`/api/v1/health` 返回 200；`/technician/`、`/admin/` 返回 200；未登录技师任务接口按预期返回 401。

## 待门店现场验收

- 需使用门店授权技师手机完成：登录 → 按沙发/房间查看顾客订单 → 确认服务 → 服务结束 → 第一屏填写年龄段、性别、体型、职业及服务参考 → 重试/重复提交幂等验证。
- 现场验收不得使用真实敏感顾客画像做测试；不涉及智慧宝派单、开房、离位、清洁或物理资源释放。

# 2026-08-29 顾客端服务位实际验收复核

## 本地完成

- 顾客端全量测试：`149 passed / 0 failed / 1 skipped`。
- 顾客端生产构建成功：Vite 转换 `2013` 个模块，主 bundle `416.65 kB`（gzip `129.56 kB`）。

## 已发布生产验证

- 使用独立浏览器配置和全新标签完成只读验收，未读取或填写敏感凭据。
- `seat=sofa-05` 入口顶部显示 `5号沙发`；独立 `seat=sofa-06` 入口顶部显示 `6号沙发`，二维码服务位未被旧会话覆盖。
- 同一设备已有 5 号绑定时再次打开 6 号会被设备锁拦截并提示当前绑定 5 号，不会静默切换或串位；这是当前“仅前台可换位”的预期边界。
- 6 号详情页只显示当前项目门店价/会员参考价；加入草本泡脚后底部草稿显示 `预计合计 ¥39.9`，未带入其他项目总价；控制台无 error/warn。
- 刷新过程中出现一次短暂 `502 Bad Gateway`，约 5 秒后重试恢复正常；服务器 API 日志显示请求均返回 200，需继续观察容器重建期间的反向代理可用性。

## 待现场验收

- 仍需两台真实门店设备分别扫码，验证跨设备并发、断网恢复、服务状态同步、超时释放及智慧宝并行操作。
- 提交给前台属于真实业务写入，本轮未执行；需要在现场即将提交前由负责人确认测试服务位和测试订单范围。

# 2026-08-29 顾客端轻动效 release 发布与线上复核

## 本地完成

- 顾客端全量测试：`149 passed / 0 failed / 1 skipped`。
- 顾客端生产构建成功：Vite 转换 `2013` 个模块，主 bundle `416.65 kB`（gzip `129.56 kB`）。

## 已发布生产

- 新 release：`customer-motion-20260829-1`，仅替换 `diy-web/dist`，保留线上后端、管理端和数据库不变。
- 远端逐文件 `MANIFEST.sha256` 校验通过并完成 `current` 原子切换；Manifest 文件 SHA-256：`3fba21878d317aa1eb1d489141210cb36372222015cb4b82357f163750c4b1a4`。
- `https://diy.hexiaoyue.com/api/v1/health` 返回 `status: ok`，顾客端首页返回 HTTP 200。
- 无痕移动端复核通过：`sofa-05` 显示 5 号沙发；详情顶部只显示当前项目价格，底部只显示当前项目配置价；控制台无 error/warn。
- 线上截图：`output/playwright/customer-motion-20260829.png`。

## 待现场验收

- 本轮未提交真实营业选单，未发送短信，未改变服务位状态。
- 真实会员、多设备并发、断网恢复、超时释放、技师确认/结束、画像记录和评价闭环仍需门店授权设备现场验收。

# 2026-08-29 管理后台数据访问契约修复（本地完成，未发布）

## 本地完成

- 修复 `AdminDataProvider.update()` 无条件注入当前 `store_id` 的问题；普通资源 PATCH 现在保持调用方原始字段，只有显式传入 `store_id` 时才执行当前门店绑定校正。
- 保留创建资源时的门店绑定、缓存失效、版本 `If-Match`、401 登录失效和错误归一化行为，避免影响既有门店资源流程。

## 涉及文件

- `admin-react/src/core/dataProvider/index.ts`
- `admin-react/tests/dataProvider.test.ts`

## 测试结果

- 管理端全量测试：`105 passed / 0 failed`。
- 管理端 TypeScript 检查：`npx tsc -b` 通过。
- 管理端生产构建：通过；Vite 转换 `3999` 个模块，主 bundle 约 `2.27 MB`，保留既有大于 500 KB 的拆包警告。
- 后端专项命令 `tests/test_api_contracts.py tests/test_admin_catalog_options_api.py -k "project or catalog"`：`18 passed / 7 failed / 31 deselected`。失败主要为既有 `ROLE_MIGRATION_REQUIRED` 员工角色迁移夹具（返回 403），另有一条严格项目创建返回码预期与当前实现不一致；未发现由本轮管理端 PATCH 负载修复引起的失败。
- 源码目录 `C:\Users\gaoji\WorkBuddy\2026-07-31-12-31-02` 当前不是 Git 仓库，无法提供该目录的 `git diff`/提交状态；未执行任何清理或回滚操作。

## 发布状态

- 已发布生产：否。本轮仅完成本地代码、测试和构建，未连接服务器、未修改数据库、未切换生产 `current`。
- 生产 release：未改变，继续以服务器实际 `readlink` 结果为准。

## 待现场验收与后续

- 需使用门店授权管理员账号验证项目、商品、技师资源的真实 PATCH/创建权限和门店隔离；使用普通员工、技师账号复核只读边界。
- 后端角色迁移契约和严格项目创建返回码需单独确认后再修复，避免将历史测试夹具问题混入本轮管理端迁移。
- 正式发布前仍需数据库备份、迁移演练、Manifest 校验、线上健康检查和门店现场闭环验收。

# 2026-08-29 管理后台路由级懒加载（本地完成，未发布）

## 本地完成

- `MainLayout` 中各管理页面改为 `React.lazy` 动态导入，路由区域增加统一 `Suspense` 加载态；未改变现有角色权限、导航路径和业务页面契约。
- 页面资源已按路由拆分，项目、商品、技师、服务位等页面不再随首屏同步加载；共享 Ant Design/ProComponents 依赖仍需后续按构建分析继续拆分。

## 涉及文件

- `admin-react/src/layouts/MainLayout.tsx`
- `admin-react/tests/navigation-boundary.test.ts`

## 测试结果

- 管理端全量测试：`107 passed / 0 failed`。
- 管理端生产构建：通过，Vite 转换 `4000` 个模块；入口 chunk 约 `0.40 kB`，页面 chunk 已独立生成；共享依赖仍有约 `1.23 MB` 与 `710 kB` chunk，保留既有大 chunk 警告。

## 发布状态

- 已发布生产：否。本轮仅完成本地路由装载优化和测试，未连接服务器、未修改数据库、未切换生产 `current`。
- 生产 release：未改变，继续以服务器实际 `readlink` 结果为准。

## 尚未完成事项

- 继续依据构建产物分析共享依赖，评估 `manualChunks` 或按功能域拆分，避免一次性引入完整 ProComponents。
- 发布前需重新执行管理端生产包 Manifest 校验、线上健康检查和授权账号现场验收。

# 2026-08-29 管理后台路由懒加载复验（本地完成，未发布）

## 本地完成

- 按 React bundle 优化规范复验路由动态导入；项目、商品、技师、服务位等页面均通过 `React.lazy` 按需加载，并由 `Suspense` 提供统一加载态。
- 未改变权限判断、导航注册表、业务 API 或智慧宝物理资源边界。

## 涉及文件

- `admin-react/src/layouts/MainLayout.tsx`
- `admin-react/tests/navigation-boundary.test.ts`

## 测试结果

- 管理端全量测试：`107 passed / 0 failed`。
- 管理端生产构建：成功，Vite 转换 `4000` 个模块；入口 chunk `0.40 kB`，页面 chunk 已拆出；共享依赖仍有约 `1.23 MB` 与 `710 kB` 大 chunk 警告。

## 发布状态

- 已发布生产：否。本轮仅本地完成，未连接服务器、未修改数据库、未切换生产 `current`。
- 生产 release：未改变，继续以服务器实际 `readlink` 结果为准。

## 尚未完成事项

- 后续可基于构建分析评估 `manualChunks` 或按功能域拆分共享依赖；需先确认部署缓存策略，避免增加首屏请求数量。
- 发布前仍需 Manifest 校验、线上健康检查和管理员/店长/员工/技师授权账号现场验收。

# 2026-08-29 共享依赖拆分评估（本地完成，未发布）

## 评估结论

- 试验按 React、Ant Design、ProComponents、Refine 配置 Vite `manualChunks`；构建虽成功，但生成空的 `antd-pro` chunk，Ant Design 共享 chunk 增至约 `1.88 MB`，首屏边界变差。
- 已撤回该配置，保留经过验证的路由级 `React.lazy` 拆分；不把仅改善文件缓存、却增加首屏体积的方案带入生产。

## 验证结果

- 撤回后管理端生产构建再次通过，Vite 转换 `4000` 个模块；入口约 `0.40 kB`，共享 chunk 回到约 `1.23 MB` 与 `710 kB`。
- 管理端测试基线保持 `107 passed / 0 failed`（本次仅调整构建配置，未改变业务代码）。

## 发布状态

- 已发布生产：否。服务器、数据库和生产 `current` 均未修改。

## 后续事项

- 如继续优化，先引入构建可视化分析并结合部署缓存策略，再决定是否按功能域拆分 ProComponents；发布前仍需 Manifest、健康检查和授权账号现场验收。

# 2026-08-29 顾客端线上发布与无缓存验收（已发布生产）

## 本地完成

- 提交成功页底部金额统一使用按会员身份解析后的 `payableTotal`，避免会员显示门店总价或错误单项金额。
- 新增回归测试 `tests/submitted-price-markup.test.ts`。
- 顾客端测试：`150 passed / 0 failed / 1 skipped`。
- 顾客端生产构建成功，产物入口为 `index-DnOfoRRk.js` / `index-BwaaR68V.css`。

## 已发布生产

- Release：`customer-submitted-price-20260829-1`。
- 本地与服务器 Manifest 校验通过，SHA-256：`7438450a35bd2ac2f00fcc12bc038e6d58711a02800ec3726188497b909c94c6`。
- 服务器 `current` 已切换至该 release；API 容器已按线上环境重建。
- 公网入口已返回新 JS 资源；`/api/v1/health` 返回 `status: ok`、`environment: production`。

## 线上顾客端验收证据

- 无历史缓存地址：`https://diy.hexiaoyue.com/?store=1&seat=sofa-05&source=store_qr&fresh=20260829e`。
- 二维码服务位正确显示为 `5号沙发`，页面标题为“荷小悦 · 到店选项目”，DOM 正常非空。
- 草本泡脚详情页只显示当前项目价格；选择拔罐后详情底部为门店价 `¥98.9`、会员价 `¥58.9`。
- 加入草本泡脚后再打开采耳，采耳详情仍只显示自身 `¥89` / `¥59`，未串入草本泡脚金额。
- 加入采耳后重新打开草本泡脚，草本泡脚详情仍显示自身 `¥98.9` / `¥58.9`；主菜单底部显示整单合计 `¥187.9` / `¥117.9`，项目价与整单价已区分。
- 使用同一无缓存地址重新打开后，页面无白屏，草稿选单恢复为 `3` 项，底部合计保持 `¥187.9`。
- 控制台日志为空，未发现 error/warn。

## 待现场验收

- 本轮未提交真实订单，未执行会员短信登录；会员真实身份价格、提交后前台/技师状态闭环仍需门店授权手机现场确认。
- 多设备并发、断网恢复、超时释放、智慧宝并行操作、技师确认/结束、画像记录和评价流程仍不能以本轮自动化结果代替营业现场验收。

# 2026-08-29 会员态线上验收（已授权，部分完成）

## 已验证

- 使用授权会员账号完成生产环境登录（手机号和验证码未记录）。
- 登录后顶部入口变为“我的”，会员推荐价格切换为会员价；页面不显示“领券/领取优惠券”按钮。
- 项目列表会员态显示“会员¥…”主价，门店价以删除线显示。
- 草本泡脚详情底部显示“会员价 ¥29.9”，删除线显示“门店价 ¥39.9”；加购服务直接显示会员价（如拔罐 `+¥29`、局部调理 `+¥49`），无办卡/领券提示。
- 加入草本泡脚后底部清单显示 `预计合计 ¥29.9`、删除线 `门店价 ¥39.9`、`已优惠 ¥10`，符合会员最低价逻辑。

## 异常与待现场验收

- 个人中心“服务记录”接口返回“请求失败，请稍后重试”，需要后续核对生产 API 的历史记录数据或权限；不影响本轮价格展示验收。
- 本轮未提交真实订单。技师确认/服务结束、评价、断网恢复、多设备并发和超时释放仍需门店现场闭环验证。

# 2026-08-29 技师移动端区位看板修复与生产验收（已发布生产）

## 本地完成

- 技师今日页按“沙发”“房间”分组展示全部 15 个服务位（8 个沙发、7 个房间），不再只显示已有订单的区位。
- 区位卡片按空闲、待服务、服务中、已完成使用不同状态色；有订单的区位显示项目摘要，点击可查看顾客服务单。
- 保留 DIY 允许的“确认服务”“服务结束”和服务参考入口，未加入派单、接单、开房、离位、清洁或物理资源释放。

## 涉及文件

- `admin-react/src/technician/TechnicianTodayPage.tsx`
- `admin-react/src/technician/technician-mobile.css`
- `admin-react/tests/technician-workspace.test.ts`

## 测试结果

- 管理端完整测试：`107 passed / 0 failed`。
- 后端技师/画像专项测试：`21 passed / 0 failed / 1 warning`；警告为 Starlette TestClient 的既有弃用提示。
- 管理端生产构建已通过（Vite 约 `4000` 个模块，保留既有大 chunk 警告）。
- 生产健康检查：`/api/v1/health`、`/technician/`、`/admin/` 均返回 HTTP 200，健康状态为 `ok`。
- 服务器当前 release 的 `MANIFEST.sha256` 全量校验通过。

## 已发布生产

- 服务器实际 `current`：`/root/hxy-diy-20260811/releases/technician-position-board-mobile-20260829-1`。
- 发布前数据库备份：`/root/hxy-diy-20260811/backups/pre-technician-position-board-mobile-20260829-082809.dump`。
- 备份 SHA-256：`36cf565a48682f568be67c346bacd58dd24afa95be29d6183b99241fb3da26ab`。
- 本轮仅切换管理端静态资源并重建 API 容器，未改变智慧宝物理资源职责。

## 线上手机验收证据

- Playwright 会话 `tech-acceptance` 使用 390×844 视口登录技师账号，首页显示 8 个沙发和 7 个房间。
- 点击 `3号沙发` 可打开 `服务单 #325`，显示“草本泡脚”和“填写服务参考”；服务状态为“已完成”。
- 滚动到页面底部后 `7号房间` 卡片完整露出，底部固定导航未遮挡操作；控制台消息为 0（Errors 0、Warnings 0）。
- 截图：`output/playwright/technician-position-board-mobile-board.png`、`output/playwright/technician-position-board-mobile-bottom.png`、`output/playwright/technician-position-board-mobile-dialog.png`。

## 待门店现场验收

- 需用门店授权手机和测试服务位复核顾客提交后状态同步，以及“确认服务 → 服务结束 → 服务参考保存/重试”的现场网络链路。
- 需确认智慧宝开房、离位、清洁和物理资源释放仍由智慧宝执行；DIY 不做派单或资源释放。
- 现场测试不得录入真实敏感顾客画像，建议继续使用测试账号和脱敏资料。

# 2026-08-29 管理后台路由懒加载发布

## 本地完成

- 管理端 `AdminDataProvider.update()` 不再向普通 PATCH 负载隐式注入 `store_id`；显式传入时仍校正为当前门店。
- 管理端页面按路由使用 `React.lazy` 和统一 `Suspense` 加载态；未改变角色权限、导航路径和业务 API。
- 管理端测试：`107 passed / 0 failed`；TypeScript 检查通过；生产构建通过（Vite 转换约 `4000` 个模块）。

## 涉及文件

- `admin-react/src/core/dataProvider/index.ts`
- `admin-react/src/layouts/MainLayout.tsx`
- `admin-react/tests/dataProvider.test.ts`
- `admin-react/tests/navigation-boundary.test.ts`

## 已发布生产

- 发布 release：`admin-refine-lazy-20260829-1`。
- 服务器实际 `current`：`/root/hxy-diy-20260811/releases/admin-refine-lazy-20260829-1`。
- 发布前数据库备份：`/root/hxy-diy-20260811/backups/pre-admin-lazy-20260829-164856.dump`。
- 备份 SHA-256：`695fbed8e4cd141f827b66e569cd505d0ba3974f81a2cf24b8e90c5f399c5427`。
- release `MANIFEST.sha256` SHA-256：`e5d064b53647aff2fc033fd89ff9a783492e57bb5eb2cf492e89470b040e8e40`；在 release 目录内逐文件校验通过。
- 本轮仅替换管理端静态资源，未执行数据库迁移；API 容器保持运行，未改变智慧宝物理资源职责。

## 线上健康检查

- `https://diy.hexiaoyue.com/api/v1/health` 返回 HTTP 200，`status: ok`、`environment: production`。
- `https://diy.hexiaoyue.com/admin/` 返回 HTTP 200，入口加载 `index-CMRytj1K.js`；入口 JS 请求返回 HTTP 200。
- 线上管理端 dist 与本地构建产物逐文件 SHA-256 一致；API 容器状态为 `running`。

## 待现场验收与后续

- 仍需使用授权店长、普通员工和技师账号现场复核页面权限、列表读取、项目/商品/技师操作和门店隔离；不得使用真实敏感画像。
- 共享 Ant Design/ProComponents chunk 仍较大，后续先做构建可视化分析，再决定是否按功能域拆分；本轮未引入未经验证的 `manualChunks`。

> 状态更正：该 release 已被后续 `customer-profile-member-no-coupon-20260829-1` 作为 current 替代；后续 release 仍包含相同管理端静态资源，Manifest 已在服务器校验通过。

## 继续项：共享依赖拆分评估（2026-08-29）

- 复核构建产物后确认最大共享 chunk 为 `index-CMRytj1K.js`（约 1.23 MB）和 `refine-W-M66Re5.js`（约 710 KB），路由页面已独立拆分。
- 源码存在多处 Ant Design 组件按需命名导入；当前瓶颈主要来自 Ant Design/ProComponents 运行时共享依赖，不适合继续盲目增加 `manualChunks`。
- 下一步应在部署缓存策略明确后引入可视化 bundle 分析，按“首屏基础壳 / 运营看板 / 配置 CRUD”验证拆分收益，再决定是否调整构建配置；本轮未修改代码。

# 2026-08-29 管理权限 helper 健壮性修复（本地完成，未发布）

## 本地完成

- `_require_admin()` 对旧角色、非法角色或缺少技师绑定的异常输入进行结构化处理，统一返回 HTTP 403 `MANAGER_REQUIRED`，不再因 `normalize_staff_role()` 的 `ValueError` 冒泡为 HTTP 500。
- 正式角色规则未改变：总部管理员和绑定门店的店长可继续通过管理权限校验，技师仍被拒绝管理写操作。

## 涉及文件

- `hxy-server/app/api/admin_v2.py`
- `hxy-server/tests/test_admin_resource_permissions.py`

## 测试结果

- 新增回归测试先失败（旧实现抛出 `ValueError`），修复后权限专项测试：`9 passed / 0 failed`。
- 管理端完整测试：`107 passed / 0 failed`。
- 管理端生产构建：已通过（TypeScript/Vite 成功，保留既有共享 chunk 体积警告）。
- 后端全量测试：`515 passed, 13 failed, 7 skipped`。新增回归测试计入通过数；失败集中在旧测试契约与当前业务边界不一致（DIY 物理资源接口统一 410、旧 staff/临时员工角色迁移、总部/店长权限语义、正式项目数量、Alembic head、运营漏斗、coupon 旧接口及旧占用续留接口），待单独清理或更新契约。

## 发布状态

- 本轮未发布生产；服务器 `current` 与生产 release 未改变。

- 未执行生产数据库备份、Manifest 发布校验或线上切换。

## 尚未完成事项

- 处理剩余 15 个后端失败测试，区分应更新的旧契约与需要修复的真实问题。
- 完成数据库备份与恢复演练、Manifest 校验、线上健康检查、权限穿透/跨店隔离、断网恢复、并发幂等及智慧宝 Mock/真实联调后，才能进行生产验收。

# 2026-08-29 运营统计测试契约对齐（本地完成，未发布）

## 本地完成

- 修正运营汇总测试夹具：埋点事件显式写入规范化的 `EventLog.store_id`，与真实 `/api/v1/tracking/events` 接口行为一致。
- 保留生产安全规则：统计接口不信任客户端可写的 `data.store_id`，避免跨店数据串入。

## 涉及文件

- `hxy-server/tests/test_api_contracts.py`
- `hxy-server/tests/test_task2_alembic_chain.py`

## 测试结果

- 运营汇总去重/门店隔离测试：`2 passed`。
- Alembic 迁移链测试：`1 passed`；已按实际 revision `20260826_coupon_store_scope` 对齐旧断言。
- 管理端完整测试：`107 passed / 0 failed`；生产构建通过。
- 后端全量最近结果（在本次两项测试对齐前）：`517 passed, 11 failed, 7 skipped`；剩余失败仍为旧接口/旧角色/旧基线契约，未发现由本轮测试契约对齐引入的新失败。Alembic 单项随后已通过。

## 发布状态

- 本轮未发布生产，服务器 `current`、生产 release 和数据库均未改变。

# 2026-08-29 总部加项更新权限修复（本地完成，未发布）

## 本地完成

- 修复总部管理员更新加项时错误要求绑定门店的问题。
- 总部管理员现在可按主数据权限更新任意门店加项；绑定门店的店长仍只能按既有门店权限访问，不能取得总部主数据写权限。
- 加项不存在时统一返回 404，不改变现有门店隔离规则。

## 涉及文件

- `hxy-server/app/api/admin_v2.py`
- `hxy-server/tests/test_selection_closure_v2.py`

## 测试结果

- 总部加项创建、发布及顾客目录可见性测试：`1 passed`。
- 组合后端专项（选择闭环、权限、API 契约）：`68 passed, 4 failed`；剩余 4 项均为旧物理资源接口/coupon 契约，未涉及本次修复。
- 管理端完整测试：`107 passed / 0 failed`；生产构建通过。

## 发布状态

- 本轮未发布生产；服务器 `current` 与生产 release 未改变。

# 2026-08-30 三窗口共享记忆基础建立（本地完成，未发布）

## 本地完成

- 新增 `docs/TEAM-MEMORY.md`，集中记录三端共享的业务边界、权限原则、生产事实和协作规则。
- 新增 `docs/workstreams/technician.md`，记录技师端负责范围、非目标、代码目录、已确认状态和任务收尾模板。
- 约定顾客端、技师端、管理端窗口共享项目文档记忆；业务订单和服务状态仍以 API/PostgreSQL 为唯一来源，不使用浏览器缓存跨端同步。

## 涉及文件

- `docs/TEAM-MEMORY.md`
- `docs/workstreams/technician.md`
- `docs/WORK-STATUS.md`

## 验证结果

- 已核对服务器实际 `current` 为 `customer-profile-member-no-coupon-20260829-1`。
- 本轮仅新增协作文档，未修改业务代码、数据库或生产环境；未运行业务测试。

## 已发布生产

- 否。

## 待办

- 顾客端和管理端窗口分别建立 `docs/workstreams/customer.md`、`docs/workstreams/admin.md`，并沿用同一共享记忆规则。

# 2026-08-30 管理后台与员工工作台继续推进（本地完成，未发布）

## 本地完成

- 按管理端职责边界复核总部管理员、店长、普通员工与技师移动端入口，未开放跨门店数据，也未暴露智慧宝物理资源操作。
- 对齐并验证管理 API 契约：DIY 物理资源相关端点明确返回 `410 DIY_PHYSICAL_RESOURCE_FORBIDDEN`；运营统计仅接受规范化 `EventLog.store_id`；正式菜单 bootstrap 为 13 个项目；Alembic coupon scope head 为 `20260826_coupon_store_scope`。
- 修复总部管理员更新任意门店加项时错误要求绑定门店的问题；补充不存在资源的 404 保护。
- 新增/更新回归测试与管理工作流文档：`docs/workstreams/admin.md`。

## 测试结果

- 管理端完整测试：`107 passed / 0 failed`。
- 管理端生产构建：通过（TypeScript、Vite 均成功；仍有既有共享 chunk 体积警告）。
- 后端管理/权限/目录/菜单/Alembic 组合回归：`75 passed`。
- 后端 API 契约：`37 passed`。
- 后端全量最近结果：`517 passed, 11 failed, 7 skipped`；剩余失败为历史角色、旧占用续留接口等迁移契约，未作为生产通过依据。

## 发布状态

- 本地完成：以上代码和测试均在工作区完成。
- 已发布生产：无。本轮未切换服务器 `current`，未重建生产 API 容器。
- 待现场验收：店长/员工/技师真实账号的权限穿透、门店隔离、服务单闭环、断网恢复、并发幂等及智慧宝联调。

# 2026-08-30 三端窗口协作协议与启动提示词（本地完成，未发布）

## 本地完成

- 新增 `docs/AI-WINDOW-PROMPTS.md`，提供公共启动提示词以及顾客端、管理端、技师端的职责附录、分支规则和交接模板。
- README 明确本目录是 Obsidian Vault 与 GitHub 协作文档仓库，不是实际源码仓库；Obsidian 用于阅读/编辑，GitHub 用于版本、PR 和审计。
- 共享记忆补充分支/PR、跨端合同变更、端工作流缺失时的建立规则，避免三个窗口依赖彼此聊天上下文。

## 涉及文件

- `README.md`
- `docs/AI-WINDOW-PROMPTS.md`
- `docs/TEAM-MEMORY.md`
- `docs/WORK-STATUS.md`

## 验证结果

- 已从 `origin/main` 创建独立文档分支，并通过 Markdown 文件存在性、引用路径和 Git diff 空白检查。
- 本轮只修改协作文档，未修改业务源码、数据库、服务器或生产 release；不需要执行业务测试或生产构建。

## 发布状态

- 未发布生产；生产服务器、数据库和 `current` 均未修改。
- 待推送 `codex/docs/three-window-protocol` 并创建 Pull Request 后，由三个端窗口审核采用。

## 2026-08-30 三端源码基线边界更正（本地完成，未发布）

### 本地完成

- 实际核对本地目录后，明确 `hxy-diy-monorepo-bootstrap` 是包含三端源码的统一候选基线；当前分支为 `codex/admin/monorepo-bootstrap`。
- 明确 `2026-07-31-12-31-02` 顶层不是 Git 仓库，且含未提交历史改动，仅可作为迁移/生产差异核对来源。
- 明确 Obsidian 工作区是共享文档层；当前 `origin/main` 仅含文档，源码基线合并前不得从其中创建三端代码任务。

### 涉及文件

- `README.md`
- `docs/AI-WINDOW-PROMPTS.md`
- `docs/TEAM-MEMORY.md`
- `docs/WORK-STATUS.md`

### 验证结果

- 已核对三个目录的仓库根、远端、分支和工作区状态，并确认 `origin/main` 当前未包含三端源码目录。
- 本轮仅更正协作文档，未修改业务代码、数据库、服务器或生产 release。

### 发布状态

- 未发布生产。
- 待源码基线 PR 合并后，三个端窗口才可按本协议从 `origin/main` 开始独立任务。
