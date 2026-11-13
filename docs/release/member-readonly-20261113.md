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
