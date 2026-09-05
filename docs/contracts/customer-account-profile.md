# 顾客账号与“我的”契约

更新日期：2026-09-05

## 1. 适用范围

本契约约束顾客端手机号登录、会员有效期、本人到店记录、累计会员节省和服务评价。顾客端不在线支付，也不写入技师服务状态或物理服务位状态。

## 2. 单设备登录

- `users.customer_login_version` 是顾客登录会话代次，安全默认值为 `1`。
- 每次手机号验证码登录成功后，服务端递增代次，并把新代次写入 JWT 的 `login_version`。
- 所有需要顾客身份的接口必须同时校验 JWT 和数据库当前代次，禁止各接口自行只解码 `sub`。
- 旧令牌失效时返回 HTTP `401`，响应明细为：

```json
{
  "detail": {
    "code": "SESSION_REPLACED",
    "message": "账号已在另一台设备登录，请重新登录"
  }
}
```

- 顾客端收到该错误后清除本机登录令牌并回到登录态，不清除或篡改到店选单、服务状态等服务端事实。
- 顾客端在登录期间应进行短周期校验，并在页面重新可见或获得焦点时立即校验；旧设备不依赖手工刷新才感知替换。
- 部署不会主动使全部旧令牌退出；同一手机号下一次成功登录后，先前令牌开始失效。

## 3. 会员快照

`POST /api/v1/auth/h5/login` 和 `GET /api/v1/auth/h5/me` 返回：

- `is_member: boolean`
- `member_type: string|null`
- `member_expire_at: datetime|null`

会员资格、到期时间和价格均以后端事实为准。前端不得用本地缓存延长会员期或自行判定会员价格。

## 4. 本人到店记录

`GET /api/v1/selection-sessions/mine` 仅返回当前 JWT 所属顾客的记录，每条除选单快照外增加：

- `occupancy_status: string|null`
- `service_completed_at: datetime|null`
- `can_evaluate: boolean`
- `evaluated: boolean`

`GET /api/v1/selection-sessions/{id}/customer-detail` 使用相同所有权校验；他人记录按不存在处理并返回 `404`。

## 5. 评价

- `POST /api/v1/selection-sessions/{id}/feedback` 支持原选单令牌，或当前顾客 Bearer 令牌。
- Bearer 令牌只能评价本人记录。
- 只有存在权威服务结束时间时才允许评价；未结束返回 `409`。
- 同一选单重复提交评价返回已有结果，不重复创建。

## 6. 累计会员节省口径

```text
单次会员节省 = max(当次门店价快照 - 当次会员价快照, 0)
累计会员节省 = 所有已完成服务的单次会员节省之和
```

- 只统计存在 `service_completed_at` 的记录。
- 草稿、取消、过期、未完成服务不统计。
- 优惠券优惠不计入会员节省。
- 缺失或非法价格按 `0` 处理，不推测历史价格。

## 7. 兼容与发布

- 新响应字段均允许旧数据为空，顾客端须提供降级文案。
- 数据库迁移只新增带默认值字段，回滚时可删除该字段。
- 自动化测试、构建和公网探针不能替代门店现场验收。

## 8. 后续独立契约

唯一可信设备、30秒动态会员码、技师端扫码与会员价原子重算属于独立高风险发布切片，完成前不得宣称已实现。对应契约另见后续 `customer-membership-verification.md`。
