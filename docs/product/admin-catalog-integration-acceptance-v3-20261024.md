# 服务项目真实接口与后台表单隔离验收 v3

日期：2026-10-24。结论：本轮隔离实现与预览通过，未提交、未推送、未合并、未部署；生产库未写入。保留前两轮及原工作区修改。

## 工作区与隔离环境

- 实施工作区：`hxy:/root/hxy-diy-development/mobile-workbench-closeout-20261023`，分支 `codex/admin-catalog-recovery-20261024`，基线 HEAD `13ab819f793599b2d81fca6e8b57365af9594a73`。
- 真实 FastAPI 路由、认证与 SQLAlchemy；新建独立 PostgreSQL 16 容器和 internal Docker 网络，只有合成门店、账号、项目、标签和配置。
- API 单 worker，内存 512 MiB、CPU 0.5；数据库内存 384 MiB、CPU 0.35；无生产环境文件、数据库挂载或外部营销配置。API 只经 SSH 回环转发访问，未公开测试服务。
- 数据库 schema 由模型创建，本轮不做迁移验收，不修改生产结构。
- 本机仅接收哈希核验的服务器源码快照，使用既有固定依赖做受限构建和 localhost 预览；业务修改均在 hxy。

## 可复现验收结果

| 层次 | 结果 | 覆盖 |
| --- | --- | --- |
| 网络 HTTP + PostgreSQL | 21 项通过 | 实际账号登录、项目新建/编辑、列表回读、选项创建、校验、普通/会员试算、发布、权限/跨店拒绝、422 |
| 网络 HTTP + PostgreSQL | 18 项通过 | 上传缺门店 400、local 存储直接上传回退 409、multipart 上传和图片读取、跨店上传拒绝；分群/停用规则及跨店拒绝 |
| 网络 HTTP + PostgreSQL | 12 项通过 | 原发布组 PATCH 409、2 个并发建草稿只建 1 份、修改组/选择、校验发布回读、原图哈希和原价格不变 |
| 后端 ASGI / SQLite 合同 | 27 项通过 | 既有目录合同及新草稿重复调用/权限/归档限制/不可变版本；与上面的网络 HTTP 区分 |
| 前端针对性测试 | 30 项通过 | 错误安全映射、金额转换、目录校验文案、结构化业务展示及原内容保留 |
| 类型与构建 | 通过 | 受限 TypeScript noEmit；本机哈希快照 Vite 构建。既有 chunk 超 500 kB 提示保留，非构建错误 |
| 浏览器真实接口 | 通过 | 项目保存、64 字边界、已发布→创建草稿→改组保存→价格预览→发布第 3 版→返回显示只读；审计中文摘要；真实创建分群、保存停用标签规则 |

服务端根因和修复说明见 `admin-catalog-integration-prd-v3-20261024.md`。原生产截图发生时的完整失败日志未取得；不声称已还原当时唯一根因。

## 预览方式

入口：`http://127.0.0.1:4214/tests/admin-live-preview.html?page=projects`。
顶部可切换服务项目、顾客页面内容、操作记录、顾客分群、自动化规则。使用合成总部账号编辑目录；使用合成店长账号查看本店分群和规则。模拟账号选择与密码已放在仅本机预览登录页，不使用真实员工身份。

服务项目操作顺序：编辑内容 → 项目资料 → 顾客可选内容 → 创建编辑草稿 → 编辑组/选择并保存 → 检查与发布 → 发布。预览中的发布只写合成库。已发布后再次进入可选内容必须显示只读，并可再建下一版。

页面内容沿用 v2 表单；店长无该模块维护权限时正常提示，不绕过权限。自动化规则本轮仅保存停用配置，未执行引擎、发券、消息或顾客打标。分群人数来自保存的统计字段，接口不提供统计时间，不把 0 人视为实时结果。

## 证据与限制

- 服务器证据：`/root/hxy-diy-private-operations/admin-catalog-integration-20261024/state/` 下 `http-contract-results.json`、`http-extra-results.json`、`http-draft-results.json`、`catalog-contract-tests.log`、`frontend-final-tests.log`。
- 本机交付：`C:/Users/gaoji/Documents/ChatGPT/hxy-diy/output/admin-catalog-recovery-20261024/` 下浏览器截图、AX 记录、源码快照 SHA、构建日志、PRD 与本记录。
- OpenAPI 与管理端生成类型由工具重生成；新增草稿接口不需要数据库迁移。
- 未进行真实手机/企业微信现场验收，也未运行生产发布或 CI 合并流程。本轮预览依赖本机 Vite、SSH 隧道及 hxy 隔离容器存活。
