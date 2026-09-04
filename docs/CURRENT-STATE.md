# hxy-diy 当前状态

更新时间：2026-09-05 00:30（Asia/Shanghai）

本文件只记录三个开发窗口开始任务时需要知道的当前事实。发布和回滚历史保存在 `docs/WORK-STATUS.md`。

## 当前生产

- 服务器部署根目录：`/root/hxy-diy-20260811`
- Release：`main-bf0bddf-20260905-1`
- 对应主干功能提交：`bf0bddf`（PR #15）
- API 镜像：`hxy-diy-api:bf0bddf`
- Alembic head：`20260904_service_reference_v2`
- 数据库备份：`pre-main-bf0bddf-20260905-001822.dump`
- 备份 SHA-256：`9fa62d8422394d078e770978c28de25e40decc4b11734fdb34df383ada297371`
- 备份恢复演练：通过
- 公网 `/`、`/admin/`、`/technician/`、`/api/v1/health`：HTTP 200
- API 容器：运行中，发布验收时重启次数为 0，近期无异常日志
- Release Manifest：逐文件校验通过

`origin/main` 当前包含 PR #16 的测试基线修复；该提交只调整测试，不改变上述生产业务代码。

## 三端当前状态

### 顾客端

- 正式入口：`https://diy.hexiaoyue.com/`
- 当前生产构建运行正常；本次服务参考发布未改变顾客端交互。
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
