# hxy-diy 当前状态

更新时间：2026-09-05 11:12（Asia/Shanghai）

本文件只记录三个开发窗口开始任务时需要知道的当前事实。发布和回滚历史保存在 `docs/WORK-STATUS.md`。

## 当前生产

- 服务器部署根目录：`/root/hxy-diy-20260811`
- Release：`manual-2c3793ea3b95-20260905-1`
- 对应主干提交：`2c3793e`（顾客端业务 PR #18、发布流水线 PR #19）
- API 镜像：`hxy-diy-api:2c3793e`，镜像 ID `sha256:9742cd63e0ae4f1ecdc7c8862d4dc6f4fe36d7469808a2c1121aa9daf084b15b`
- Alembic head：`20260904_service_reference_v2`
- 数据库备份：`pre-manual-2c3793ea3b95-20260905-1-20260905T025134Z.dump`
- 备份 SHA-256：`e81964a2fc53455650de9cca6e88ee11ba722695e06607132078661af7e04156`
- 备份恢复演练：通过
- 公网 `/`、`/admin/`、`/technician/`、`/api/v1/health`：HTTP 200
- API 与数据库容器：运行中，发布验收时重启次数均为 0，数据库健康
- Release Manifest：逐文件校验通过；Manifest SHA-256 `2ad2123696c2e5166e837c524b2a8635053793e9097a9fae1865933f7be44c7f`

顾客端入口加载 `index-BB45yxbT.js` 与 `index-C5IUvO1n.css`；本次未执行数据库迁移。

## 三端当前状态

### 顾客端

- 正式入口：`https://diy.hexiaoyue.com/`
- 已发布服务结束后重新进入空白选购、匿名多次提交整单门店价、浏览器匿名身份自愈、底部会员价和固定高度选购抽屉修复。
- 顾客端不直接管理技师服务参考标签；未来如增加顾客确认入口，必须复用后端版本化标签契约。

### 管理端

- 正式入口：`https://diy.hexiaoyue.com/admin/`
- 已能通过后端读取顾客画像历史，但新版 `schema_version=2` 服务参考尚未形成专用、易读的管理页面。
- 下一步：正确展示新版记录；由后端提供唯一标签字典；增加门店基础聚合。不得把结构化服务参考复制为普通用户标签。

### 技师端

- 正式入口：`https://diy.hexiaoyue.com/technician/`
- 快速服务参考已发布：重点部位、避让部位、力度、温度、服务反馈、下次建议、顾客确认和可选原话。
- 技师可读取当前顾客最近一次已确认的安全摘要；跨店、非活动服务和隐私字段受后端限制。

## 当前跨端契约

- 服务参考：`schema_version=2`
- 标签体系：`taxonomy_version=service_reference_v1`
- 后端保存稳定英文编码，中文文案仅用于展示。
- 顾客表达、技师观察、顾客确认和下次建议必须分开保存。
- 结构化服务参考与普通运营标签是两类数据，不得相互自动转换。

## 开始任务

先执行 `git fetch origin`，确认当前分支基于最新 `origin/main`，再读取 `docs/CONTEXT-MANIFEST.md` 和本端 workstream。涉及生产状态时必须重新实时核验。
