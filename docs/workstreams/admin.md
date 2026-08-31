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
