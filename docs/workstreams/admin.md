# 管理后台与员工工作台工作流

更新时间：2026-08-31

## 负责范围

- 店长、总部管理员、普通员工工作台。
- 商品、项目、加项、技师档案、门店和服务位配置。
- 管理端导航、表格、表单、Refine 渐进式数据访问和门店隔离。
- 技师移动端保持独立路由；DIY 管理端不开放智慧宝派单、开房、离位、清洁或物理资源释放。

## 三端协作入口

- 统一代码仓库：GitHub `zzzai/hxydiy`。
- 管理端代码：`admin-react/`；顾客端和后端仅作为同仓库联调基线，不在本工作流中修改其业务。
- 共享记忆：`docs/TEAM-MEMORY.md`；任务交接：本目录；发布事实：`docs/WORK-STATUS.md`。
- Obsidian 打开仓库根目录即可阅读上述 Markdown；代码变更必须走 `codex/admin/<task>` 分支和 Pull Request。

## 2026-08-31 服务位二维码查看与店长配置边界（本地完成，未发布）

- 服务位看板中的“查看顾客二维码”不再受“服务位可用”状态限制；服务中、待服务等现场状态仍可查看既有码并下载有效二维码，避免临时无法补印或核对。
- 普通员工在本店可查看二维码，但页面不再展示停用、重新启用、重新生成或换绑操作；只有当前门店店长可见这些配置控制项。
- 前端权限 helper 与服务端的门店归属和 `manager` 写权限保持一致；本轮未改动二维码 API、顾客端、技师端、智慧宝或任何物理资源操作。

涉及文件：`admin-react/src/pages/ServicePositionsPage.tsx`、`admin-react/src/servicePositionQr.ts`、`admin-react/tests/qr-management.test.ts`、`docs/TEAM-MEMORY.md`。

验证：先新增并确认权限回归测试失败，再完成最小实现；管理端 `npm test` 为 119 passed，`npx tsc -b` 通过，`npm run build` 成功（Vite 转换 4001 个模块，保留既有共享 chunk 体积警告）。后端 `python -m pytest tests/test_admin_resource_permissions.py` 为 9 passed，含 1 个既有 Starlette/httpx 弃用警告。新工作树按锁文件执行 `npm ci` 后发现 7 个既有依赖漏洞（2 moderate、5 high），未进行无关依赖升级。

发布状态：本地完成，分支 `codex/admin/store-position-qr`；未发布生产，未执行数据库迁移、备份、Manifest 校验、服务器 `current` 切换或线上健康检查。

待现场验收：使用授权店长与普通员工账号分别验证服务中服务位的二维码查看、有效码下载、店长二维码变更入口与普通员工无变更入口；自动化测试不等于真实门店营业验收。

## 2026-08-31 服务位停用与现场二维码简化（本地完成，未发布）

- 服务位看板为店长新增“停用服务位/重新启用服务位”入口；仅无活动占用的本店实际服务位可操作，普通员工不显示入口。
- 停用仅写入 DIY 的 `operational_status`：阻止新的顾客扫码和共享 iPad 入口，不调用智慧宝开沙发、开房、离位、清洁或物理资源释放。服务端同时校验店长角色、门店归属、实际服务位和活动占用，并记录前后状态及原因审计。
- 服务位停用后不再新建二维码；已有二维码绑定保留，恢复服务位后可继续使用。新生成二维码使用紧凑 v3 令牌，旧 v2 印刷码继续兼容；前端二维码使用 `M` 级纠错、1024 像素输出和标准 4 模块静区，减少码图模块密度并提升现场打印扫码容错。
- 发现现有普通员工认证缺口：未迁移的 `staff` 账号在登录层即返回 `ROLE_MIGRATION_REQUIRED`，无法进入“只读二维码”现场验收；本轮未改后端权限模型，必须作为独立角色迁移任务处理。

涉及文件：`admin-react/src/pages/ServicePositionsPage.tsx`、`admin-react/src/servicePositions.ts`、`admin-react/src/servicePositionQr.ts`、`admin-react/src/api.ts`、`hxy-server/app/api/occupancies.py`、对应管理端/后端测试及 `docs/TEAM-MEMORY.md`。

验证：先新增并确认前端缺失导出、后端缺失 v3/停用接口的失败测试，再完成最小实现。管理端 `npm test` 为 121 passed，`npx tsc -b` 通过，`npm run build` 成功（Vite 4001 modules，保留既有共享 chunk 体积警告）。后端 `python -m pytest tests/test_admin_resource_permissions.py tests/test_occupancy_api.py -q` 为 45 passed，含 1 个既有 Starlette/httpx 弃用警告。

发布状态：本地完成，分支 `codex/admin/store-position-qr`；未发布生产，未执行数据库迁移、备份、Manifest 校验、服务器 `current` 切换或线上健康检查。

待现场验收：待发布后使用店长账号验证空闲服务位停用、扫码拒绝、重新启用和原二维码恢复；用已迁移为正式普通员工的账号验证只读二维码边界。不得在营业服务位上执行停用、重新生成或换绑测试。

## 本轮完成

- 管理权限 helper 对旧/非法角色统一返回结构化 403，避免 `ValueError` 变成 500。
- 总部管理员更新任意门店加项时不再错误要求绑定门店；店长权限边界保持不变。
- 运营统计测试夹具与真实埋点契约对齐，统计继续只信任规范化 `EventLog.store_id`。
- 对已下线的 DIY 物理资源接口更新契约测试，明确返回 `410 DIY_PHYSICAL_RESOURCE_FORBIDDEN`。
- 对齐正式菜单 13 项和实际 Alembic revision 的过期测试断言。

## 验证

- 管理端：`npm test`，107 passed；`npx tsc -b` 通过；`npm run build` 成功（Vite 4000 modules）。
- 后端管理/权限/目录/菜单/Alembic 组合回归：75 passed。
- 后端 API 契约：37 passed。
- 最新后端全量：`525 passed, 4 failed, 7 skipped`；4 个失败均为旧 `staff` 临时角色/占用续留迁移契约，当前实现按正式角色规则返回 `403 ROLE_MIGRATION_REQUIRED`，未作为生产通过依据。
- 构建仍有既有共享 chunk 体积警告（约 1.23 MB、710 KB），不影响构建成功。

## 发布与验收

- 本轮未发布生产，服务器 `current` 与生产 release 未改变。
- 待完成数据库备份与恢复演练、Manifest 校验、线上健康检查、跨店权限穿透、断网/并发幂等和智慧宝联调后，再安排生产发布与现场验收。

## 2026-09-03 服务位停用统计修复（本地完成，未发布）

- 修复服务位统计将停用服务位误计入“空闲”的问题，新增“已停用”数量并在管理端房态看板展示。
- 兼容 FastAPI `Query` 默认值的项目列表分页参数，更新店长项目上下架权限回归覆盖。

涉及文件：`hxy-server/app/api/admin_v2.py`、`hxy-server/tests/test_api_contracts.py`、`admin-react/src/pages/RoomsPage.tsx`、`admin-react/tests/rooms.test.ts`。

验证：管理端 `npm test -- --run` 125 passed；`npx tsc -b` 通过；`npm run build` 成功（保留既有大 chunk 警告）；后端管理专项 93 passed，1 个既有 Starlette/httpx 弃用警告；`git diff --check` 通过。

发布状态：本地完成，未发布生产，未执行数据库备份、Manifest 校验、线上切换或健康检查；生产 release 未改变。

待现场验收：发布后由店长验证非营业服务位停用/启用、扫码拒绝与恢复；普通员工确认无运营状态操作入口，并完成门店隔离与智慧宝只读边界验收。

## 2026-08-30 媒体上传能力（本地完成，未发布）

- 新增门店隔离媒体元数据与上传/列表/受控预览/软删除 API；限制图片类型为 JPG、PNG、WebP、GIF，单文件最大 5MB。
- 店长只能操作绑定门店；总部管理员上传时必须显式指定门店；跨店访问和删除返回 404；上传与删除写入审计日志。
- 项目主图、项目详情图片模块、商品图片和加项图片改用 `MediaUploadField`，不再要求人工填写图片地址；预览通过带认证的 API 请求加载。

涉及文件：`hxy-server/app/api/media.py`、`hxy-server/app/models/media.py`、`hxy-server/alembic/versions/20260830_media_assets.py`、`admin-react/src/components/MediaUploadField.tsx` 及对应页面/API/测试。

验证：管理端 `npm test` 109 passed；`npx tsc -b` 通过；`npm run build` 成功；后端媒体、权限和目录专项 34 passed（1 个既有 Starlette/httpx 弃用警告）。

发布状态：未发布生产，未执行数据库迁移、OSS 配置和线上切换；待 CI、备份恢复、Manifest、健康检查及门店现场验收。

## 2026-08-30 七牛私有 CDN 连通性验证与签名 URL 修复（本地完成，未发布）

- 使用服务器 `/root/qiniu` 中的环境变量进行一次性真实探针，未输出或保存 AK/SK，测试对象已清理。
- 结果：上传 HTTP 200；绑定域名匿名读取 HTTP 403（空间为私有访问）；使用七牛签名下载读取 HTTP 200；删除 HTTP 200。
- 适配器现通过 `QINIU_SIGNED_URL_TTL_SECONDS`（默认 600 秒）生成短期签名 URL，避免管理端拿到不可访问的裸地址。
- 管理端 `npm test` 109 passed；TypeScript 检查和生产构建通过；后端媒体专项 11 passed。
- 尚未发布生产，服务器 `current`、数据库和 API 容器未修改；待单独发布确认后执行备份、Manifest、重建和线上验收。

## 2026-08-30 商品管理编辑与门店上下架（本地完成，未发布）

- 商品管理页新增总部商品编辑入口，编辑表单自动回填价格（分转元）和七牛媒体；总部账号不再因未绑定门店而被错误拦截。
- 总部新建商品时必须选择目标门店；更新负载不携带 `store_id`，避免通过编辑改变门店归属。
- 绑定门店店长不显示新建和主数据编辑入口，只能在本店商品列表切换“上架/下架”；商品状态展示覆盖草稿、待发布、已发布、已下架和总部强制下线。
- 后端新增严格 `PATCH /api/v1/admin/v2/products/{id}` 契约，保留旧 POST 更新路径兼容；总部可改主数据，店长仅可改 `publication_status`，不能恢复总部强制下线商品。
- 商品列表支持 `page`、`page_size`、`product_type` 筛选和服务端总数；不带分页参数时继续返回旧数组，门店选择器支持关键词搜索。

涉及文件：`admin-react/src/pages/ProductsPage.tsx`、`admin-react/src/pages/products-page-model.ts`、`admin-react/tests/products-page-model.test.ts`、`hxy-server/app/api/admin_v2.py`、`hxy-server/tests/test_api_contracts.py`、`docs/TEAM-MEMORY.md`。

验证：管理端完整测试 114 passed；`npx tsc -b` 通过；生产构建成功（Vite 4001 modules，保留既有大 chunk 警告）；后端商品/权限专项 52 passed（1 个既有 Starlette/httpx 弃用警告）。后端完整套件另有 16 个既有基线/发布环境失败，未涉及本次商品改动。

发布状态：本地完成，未发布生产；未执行数据库迁移、备份、Manifest 校验或线上切换。待完整验证、PR/CI 审核及总部、店长账号现场验收。

## 2026-08-31 项目管理权限与分页契约收口（本地完成，未发布）

- 总部管理员可跨门店查看项目、在新建时显式选择目标门店，并可编辑主数据或强制下线。
- 店长仅能查看本店项目并切换“上架/下架”；不显示新建和编辑入口，已被总部强制下线的项目不能恢复。
- 项目列表的分类、状态和分页改为服务端执行，分页响应携带准确 `total`；未传分页参数的旧客户端仍收到历史数组响应。
- 项目创建和更新审计记录目标 `store_id`，以便跨店总部操作可追溯。
- 状态 `archived` 的操作文案统一为“总部强制下线”，避免与可恢复的普通归档混淆。

涉及文件：`admin-react/src/pages/ProjectsPage.tsx`、`admin-react/src/pages/projects-page-model.ts`、`admin-react/tests/projects-page-model.test.ts`、`hxy-server/app/api/admin_v2.py`、`hxy-server/tests/test_admin_catalog_options_api.py`、`docs/TEAM-MEMORY.md`。

验证：管理端 `npm test` 116 passed；`npx tsc -b` 通过；`npm run build` 成功（Vite 4001 modules，保留既有大共享 chunk 警告）；后端目录与权限专项 34 passed，含 1 个既有 Starlette/httpx 弃用警告。当前任务工作树缺失锁定的开发依赖，已用 `npm ci --ignore-scripts` 按锁文件恢复；审计提示 7 个既有 npm 漏洞，未做无关依赖升级。

发布状态：未发布生产，未执行数据库迁移、备份、Manifest 校验、服务器切换或线上健康检查。待 Pull Request/CI 审核后，以总部管理员和店长真实账号完成跨店可见范围、目标门店选择、上架/下架及强制下线不可恢复的现场验收。

## 2026-08-31 PR 自动化验收

- 新增 GitHub Actions 工作流 `.github/workflows/ci.yml`；Pull Request 与 `main` 推送会自动执行管理端 `npm test`、`npx tsc -b`、`npm run build`，以及后端服务位/权限专项测试。
- 工作流仅执行测试和构建，不执行生产发布、数据库迁移、七牛写入或任何智慧宝物理资源操作。
- 补充服务位二维码回归保护：已替换二维码不可再次重生、停用服务位不可生成新码；公网入口禁止伪造内部 `bound_qr` 来源，均有后端契约测试覆盖。
- 生产环境不再接受无法撤销的 v1 服务位二维码，统一提示更换 v2/v3 码；本地迁移测试仍保留 v1 兼容读取。

## 2026-08-31 CI 自动验收环境修复

- `.github/workflows/ci.yml` 使用 Node 22 执行管理端测试、TypeScript 检查和生产构建，匹配当前 `node --experimental-strip-types` 测试入口。
- 后端 CI 在安装业务依赖时显式安装 `pytest`，避免云端出现 `No module named pytest` 的环境性失败。
- 首次 CI 失败已完成根因定位；修复仅涉及工作流，不涉及业务代码和生产配置。
- GitHub Actions 运行 `33387935310` 已通过：管理端测试与构建、后端权限与服务位契约两个 job 均成功。

## 2026-09-01 服务位看板运营状态收口（本地完成，未发布）

- 服务位看板和房间配置统一读取 `operational_status`；停用服务位显示为“已停用”，不再计入“可用”统计，也不显示“可接待”状态。
- 房间列表 API 返回 `operational_status`，房间配置页沿用既有服务位运营状态命令；停用/重新启用仍仅限店长或总部管理员，且活动占用时禁止操作。
- 该状态只影响 DIY 扫码和共享入口，不操作智慧宝物理资源；顾客端、技师端业务未修改。

涉及文件：`admin-react/src/pages/RoomsPage.tsx`、`admin-react/src/pages/ServicePositionsPage.tsx`、`admin-react/src/rooms.ts`、`admin-react/src/servicePositions.ts`、对应测试、`hxy-server/app/api/admin_v2.py`。

验证：管理端 `npm test` 124 passed，`npx tsc -b` 通过，`npm run build` 通过；后端服务位 40 passed、权限 9 passed。`tests/test_api_contracts.py` 仍有 2 个历史契约失败：分页函数直调的 FastAPI `Query` 默认值兼容问题，以及旧测试要求店长修改为 `candidate`，均未纳入本轮服务位改动。

发布状态：本地完成，未发布生产，未执行数据库备份、Manifest 校验、服务器 `current` 切换或线上健康检查。

待现场验收：发布后在非营业服务位验证店长停用/启用、扫码拒绝与恢复；确认普通员工无运营状态操作入口，并完成跨店隔离和智慧宝只读边界验收。

## 2026-09-03 PR 门禁：本机 AI 审查模式（本地完成，未发布）

- 云端 AI 审查改为可选项：未配置 `OPENAI_API_KEY` 时，工作流明确标记为跳过并成功结束，不上传或读取本机 Codex 配置。
- 自动合并仅以可信 PR 门禁发布的静态合同、管理端、顾客端、后端测试结果为依据；不再将云端 AI 审查列为必需检查。
- 本机 AI 审核仍作为人工发起/本机执行的审查步骤；它不替代 CI、线上发布门禁或门店现场验收。

涉及文件：`.github/workflows/ai-pr-review.yml`、`.github/workflows/auto-merge.yml`。

验证：`git diff --check` 通过；待推送后由 GitHub Actions 对 PR #10 重新运行工作流验证。未发布生产，未执行数据库变更或生产操作。
