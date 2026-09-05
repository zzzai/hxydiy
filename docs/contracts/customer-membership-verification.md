# 会员本人动态核验契约

更新日期：2026-09-05

## 安全模型

- 会员权益启用同时要求：有效会员、当前唯一登录会话、唯一可信设备、30秒一次性动态码、授权员工现场扫码、本店选单绑定。
- 可信设备凭证仅保存于 `Secure + HttpOnly + SameSite=Lax` Cookie；服务端只保存 SHA-256 哈希，不采集硬件指纹。
- 每个会员最多一个 `active` 可信设备；清除浏览器数据、无痕模式或更换浏览器均视为新设备。
- 动态码只包含高熵随机令牌，不包含手机号、姓名、会员状态或价格。

## 状态机

```text
issued -> scanned_pending -> consumed
issued/scanned_pending -> expired | revoked | rejected
```

- 新码签发时撤销同会员旧 `issued` 码；有效期固定30秒。
- 扫码预检锁定操作员工与门店；绑定时再次校验码、会员、设备、员工、门店和选单。
- 消费通过数据库行锁、唯一幂等键和单事务完成；重放、跨店、跨员工接管均拒绝。

## API

- `POST /auth/h5/trusted-device/enroll`：仅在会员没有活动可信设备时首次绑定。
- `POST /auth/h5/member-code`：仅可信设备签发动态码。
- `POST /technician/membership-verification/scan`：技师或店长预检并锁定动态码。
- `GET /technician/membership-verification/selections`：只返回当前门店待服务/服务中的最小选单摘要。
- `POST /technician/membership-verification/consume`：将已核验会员绑定本店选单并由服务端重算价格。
- `GET /admin/v2/users/{id}/trusted-device`：店长查看最小设备状态。
- `POST /admin/v2/users/{id}/trusted-device/revoke`：店长填写原因后撤销设备和未消费码并写审计。

## 权限和边界

- 技师与店长共享移动扫码入口，但店长不因此获得技师确认/结束服务权限。
- 扫码不确认服务、不结束服务、不释放或改变物理服务位，也不写智慧宝状态。
- 管理后台只处理换绑与审计，不承担日常扫码，不提供手机号直接套会员价或前端手改价格。
- 未完成动态核验的选单按门店价作为应提交价格；顾客端可以展示会员参考价，但不能自行应用会员价。

## 隐私与审计

- 技师端仅显示脱敏姓名、脱敏手机号、会员到期日和本次核验结果。
- 设备撤销与会员核验均写 `AuditLog`，包含门店、操作者、选单和结果所需的最小字段。
- 不保存证件影像、IMEI、通讯录、广告ID或人脸数据。
