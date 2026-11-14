# 顾客会员卡只读概览（2026-11-13）

## 发布事实

- PR #497；合并 `d50941d67579944a201464b4931e40aad3808efd`
- CI 43456867992 success
- Deploy 43457778128 success
- current `github-d50941d67579-43457778128`
- public health `ok/production`
- 匿名 `GET /api/v1/auth/h5/membership-overview` 返回 401

## 内容

- 新增本人只读 `GET /api/v1/auth/h5/membership-overview`；会话取 user，不接受手机号/user_id 查询。
- 逐卡展示卡类型/状态/门店/期限/权益；储值卡展示来源余额快照和核验日期；年度卡余额不适用。
- `balance_cents` 只称来源快照，不称本金、不拆赠金、不进入 DIY 钱包/充值/订单/营收。
- 历史消费/优惠未接入，金额 null、状态未核实；不显示假0。
- 来源卡显式按 `source=meiguanjia_export`、`store_id=1` 过滤；不用旧 `membership_store_id` 限制；异来源/跨店不纳入；身份复用既有权益并集。
- 页面有换号/关闭/迟到401/网络错误重试的真实 React 行为测试。

## 验证

- 后端定向 27 passed/9 subtests
- diy-web build 通过；380 tests/379 passed/1 skipped
- admin build 通过；321 tests
- 合成页面预览：`http://127.0.0.1:4179/?store=1`，截图 `evidence/member-readonly-preview.png`

## 保护

无数据库迁移、无会员导入、无历史账单导入、无余额更新、无旧数据修改、无15卡恢复、无外部登录采集/凭据读取。

## 待人工

门店19项、Excel/WPS、真实微信/摄像头/现场本人核验。

## 部署与恢复证据（2026-11-14 补录，只读）

### 实际日志/命令证据（本次直接核验）

- 备份 `pre-github-d50941d67579-43457778128-20261113T161859Z.dump`（890563 bytes）存在；`sha256sum -c` 返回 `OK`，SHA256 `8d8f73a21501d53e05fb0784aca6fb4899567a9474476b26ccb0b2d58eab87b6`。
- 运行容器 `hxy-diy-api`：`customer_membership.py` SHA256 `e2d1bba7ad8d6e89a51367646ff05ee9f63ebe0c0156d04788515559d91f71da`、`member_sync_receipts.py` SHA256 `53095e5f222da3e4c89d61227b9bcca4548629512fa32017b5e0df2258ac963c`，与合并 `d50941d6` 期望一致。
- 健康：`docker exec hxy-diy-api` 请求 `/api/v1/health` 返回 `{"status":"ok","service":"hxy-customer-api","environment":"production"}`。
- GitHub Actions Deploy `43457778128` 状态 success（发布事实已记录）。

### 由强制门禁推断（非独立恢复回执）

- 部署脚本 `deploy-production.sh` 在切换新 release 前：`pg_dump` 备份并 `sha256sum -c` 校验；`pg_restore --exit-on-error` 到独立 rehearsal 库并 `SELECT 1`（L146–152），成功后才 guarded release 切换，演练库随后删除。
- 因此「Deploy success + 备份 checksum OK」可推断本次隔离恢复演练通过；未保留独立 rehearsal 库回执，不声称有独立恢复回执。
- `.deploy.lock`（0 字节）与 mtime 不能证明无活跃部署；发布是否活跃由受控锁/脚本状态判定，不以 0 字节锁文件作证据。
