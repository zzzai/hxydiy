# 管理后台与员工工作台工作流

更新时间：2026-08-30

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
