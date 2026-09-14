# 管理端门店员工账号契约

## 范围与角色

- 此接口只维护正式门店 `manager`（店长）和 `staff`（门店员工）登录账号。
- 只有未绑定门店的 `admin`（总部管理员）可以读取、创建或更新；绑定门店的历史 `admin`、店长、普通员工和技师一律不得调用。
- `staff` 必须同时处于 `active` 状态且绑定具体门店，才能登录；其已有限制为只读运营白名单不变。
- 技师账号仍由 `/admin/v2/technicians/*` 生命周期接口维护；任意 `technician` 或关联 `technician_id` 的账号，以及 `admin`，在此接口更新时返回 `409 STAFF_ACCOUNT_MANAGED_ELSEWHERE`。

## HTTP 接口

### 列表

`GET /api/v1/admin/v2/staff?store_id=&status=&page=1&page_size=20`

- 返回 `{items, total, page, page_size}`；`items` 仅包含未关联技师的 `manager` / `staff`。
- `page >= 1`，`1 <= page_size <= 100`。
- 单项仅返回 `id`、`username`、`name`、`role`、`store_id`、`status`、`created_at`；绝不返回密码、密码哈希或登录令牌。

### 创建

`POST /api/v1/admin/v2/staff`

```json
{
  "username": "front-desk-01",
  "password": "at-least-eight-characters",
  "name": "前台员工",
  "role": "staff",
  "store_id": 12,
  "status": "active"
}
```

- `username` 为 3–32 位字母、数字、点、下划线或连字符，且全局唯一；重复返回 `409 STAFF_USERNAME_EXISTS`。
- 密码为 8–128 位，只在请求中使用，服务端加密保存且响应不回显。
- `role` 只能为 `manager` 或 `staff`；`status` 只能为 `active` 或 `disabled`；`store_id` 必须指向存在的门店。

### 编辑

`PATCH /api/v1/admin/v2/staff/{staff_id}`

- 可更新 `name`、`role`、`store_id`、`status` 与 `password`；登录名不可修改。
- 角色、门店、状态或密码任一变化时，`credentials_version` 必须递增，旧 JWT 随即返回 `401 STAFF_SESSION_REVOKED`；`disabled` 账号返回 `401 STAFF_ACCOUNT_UNAVAILABLE`。
- 调岗后，新审计记录归属新门店；创建审计归属被创建账号的目标门店。

## 审计与边界

- 创建写入 `create_staff_account`，更新写入 `update_staff_account`；审计详情只记录角色、门店、变更字段和是否撤销会话，不记录密码或密码哈希。
- 此契约不提供手机号、短信、动态码或会员价旁路；会员本人短信自助换机仍由年度会员契约处理。
