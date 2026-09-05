# hxy-diy 当前状态

更新时间：2026-09-05 12:00（Asia/Shanghai）

本文件只记录三个开发窗口开始任务时需要知道的当前事实。发布和回滚历史保存在 `docs/WORK-STATUS.md`。

## 当前生产

- 服务器部署根目录：`/root/hxy-diy-20260811`
- Release：`manual-fd58312185ae-20260905-2`
- 对应主干提交：`fd583121`（顾客端匿名选购清单逐项会员价 PR #21）
- API 镜像 ID：`sha256:6be07a904832fa2fc239def7bc010217d3934921321c0b2118d2c945ec924d1e`
- Alembic head：`20260904_service_reference_v2`
- 数据库备份：`pre-manual-fd58312185ae-20260905-2-20260905T035528Z.dump`
- 备份 SHA-256：`fb0b70d0101ead825e2bc0405a238aa8cb3bbe176806627afb49d449fd5b2e1f`
- 备份恢复演练：通过
- 公网 `/`、`/admin/`、`/technician/`、`/api/v1/health`：HTTP 200
- API 与数据库容器：运行中，发布验收时重启次数均为 0，数据库健康
- Release Manifest：逐文件校验通过；Manifest SHA-256 `be93e898cfd3f8fd09f09de98e266fb3890c1632c4ea470bd49f3e6bfd1e0950`

顾客端入口加载 `index-C3V8Tw16.js` 与 `index-BPbw_Ea8.css`；本次未执行数据库迁移。

## 三端当前状态

### 顾客端

- 正式入口：`https://diy.hexiaoyue.com/`
- 已发布服务结束后重新进入空白选购、匿名多次提交整单门店价、浏览器匿名身份自愈、底部会员价和固定高度选购抽屉修复；匿名/非会员在选购清单中可逐项看到低于门店价的会员价参考。
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
