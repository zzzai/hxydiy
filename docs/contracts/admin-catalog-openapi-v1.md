# 管理端项目与商品 OpenAPI 契约 v1

## 范围

首期只覆盖 `/api/v1/admin/v2/projects` 与 `/api/v1/admin/v2/products` 下的管理接口。它把既有请求、响应和 Bearer 登录方式写入机器可读 OpenAPI，不改变价格、权限、门店隔离、发布状态或旧路径兼容逻辑。

## 权威来源

- 后端运行时契约由 `hxy-server/app/main.py` 的 FastAPI 应用生成。
- 固化快照为 `hxy-server/openapi.json`，只能由 `python scripts/export_openapi.py` 生成，不手工编辑。
- 管理端类型为 `admin-react/src/generated/openapi.d.ts`，只能由 `npm run generate:api-types` 生成，不手工编辑。
- `projects-page-model.ts` 与 `products-page-model.ts` 直接引用生成的 `AdminProject`、`AdminProduct`，不再各自维护重复结构。

## 兼容边界

- 项目和商品列表未传分页参数时继续返回数组；传入 `page` 或 `page_size` 时继续返回 `items/total/page/page_size`。
- 既有 POST 更新路径继续保留；管理端优先使用 PATCH。
- 认证仍使用 `Authorization: Bearer <token>`。OpenAPI 中以 `StaffBearer` 表示，不把令牌写入规格或生成文件。
- 本契约只描述现有服务端校验；前端生成类型不能替代服务端权限、门店范围和业务规则验证。

## 漂移检查

CI 与可信 PR 门禁分别重新导出 OpenAPI、重新生成管理端类型，并要求工作区无差异。任何后端契约变更若未同步提交快照与前端类型，检查必须失败。

## Schemathesis 首期边界

- 在隔离的 SQLite 测试库和进程内 ASGI 应用上生成项目、商品列表的合法查询组合，并按 OpenAPI 校验响应。
- 首期仅自动调用两个 GET 列表接口；创建、更新、复制、归档等写接口只检查静态规格，不执行随机请求。
- 测试不连接生产或共享测试环境，不使用真实账号、令牌或业务数据。
- 扩大到写接口前，必须为每次测试提供独立数据库事务或可验证的清理机制，并单独评审价格、权限、门店隔离和幂等风险。

## 验收

- 六个主要列表、创建、PATCH 接口均声明 `StaffBearer` 和非空成功响应模型。
- Schemathesis 对项目、商品 GET 列表的生成式响应校验通过。
- 后端契约测试、管理端测试与生产构建通过。
- 连续执行生成命令不会产生 Git 差异。
