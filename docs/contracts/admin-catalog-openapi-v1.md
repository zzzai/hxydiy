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
- 项目和商品列表的 `store_id` 只接受正的 64 位有符号整数；`page` 上限为 `92233720368547759`，确保与最大 `page_size=100` 组合时数据库偏移量仍在 64 位有符号整数范围内。越界请求返回 `422`，不得进入数据库查询后变成 `500`。
- 既有 POST 更新路径继续保留；管理端优先使用 PATCH。
- 认证仍使用 `Authorization: Bearer <token>`。OpenAPI 中以 `StaffBearer` 表示，不把令牌写入规格或生成文件。
- 本契约只描述现有服务端校验；前端生成类型不能替代服务端权限、门店范围和业务规则验证。

## 账号、角色与工作区授权

- `Staff` 继续作为登录身份；有效权限来自 `staff_scope_assignments`，角色为 `brand_admin | hq_operator | store_manager | store_staff`。品牌角色只能使用 `brand` 范围且不绑定门店，门店角色必须使用 `store` 范围并绑定存在的门店。
- `POST /api/v1/admin/login` 在凭证通过后返回账号摘要、`selector_token` 和实时工作区列表。只有一个工作区时 `token` 已绑定该授权；多个工作区时不默认选择，`token` 与 `selector_token` 均为仅可选工作区的短期令牌；零个有效工作区返回 `403 STAFF_WORKSPACE_REQUIRED`。
- `POST /api/v1/admin/workspaces/select` 只接受选择令牌和属于该账号的有效授权，返回绑定账号、授权 ID、角色、范围和凭证版本的作用域令牌。选择令牌不能调用普通业务接口。
- 账号停用、凭证版本递增或授权停用会立即令相关作用域令牌失效。三阶段迁移期间继续接受尚未撤销的旧 `token_type=staff` 管理端令牌；技师登录契约不变。
- `brand_admin` 可管理全部授权；`hq_operator` 可管理除 `brand_admin` 外的授权；门店角色不可管理授权。最后一个有效品牌管理员不得停用。
- 授权写审计保存操作账号、当前授权、角色、范围、目标账号、目标授权以及变更前后值；密码与令牌不得写入审计。
- 历史 `admin` 账号迁移时保留密码哈希，清除固定门店并仅递增一次凭证版本；其他管理账号生成等价授权且不扩大权限，技师账号不迁移。

## 商品目录增量

- 商品管理与公开目录新增可空 `member_price_cents`、非负 `display_order` 和受控 `detail_modules`。
- 会员价有值时不得小于零或高于 `price_cents`；PATCH 显式传入 `member_price_cents: null` 表示清除。
- 详情模块仅允许 `text` 与 `image`：文字模块必须有正文，图片模块必须有图片地址，未知类型和额外字段返回 `422`。
- 管理端与公开目录按 `display_order`、商品 ID 稳定排序；旧商品迁移后顺序为 `0`、详情为空、会员价为空。
- 新字段不表示已经支持库存、支付、自提、配送或顾客端商品下单。

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
