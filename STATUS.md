# HXY 会员与回执 STATUS

更新时间：2026-11-13 23:12 Asia/Shanghai
执行方：DeepSeek Harness
控制/独立审查：Codex

## 上游批次 A（已发布）

- PR #495 合并 `16aed90999ec017114d56bbd2cb87e99e4742576`；CI 43444886747 success；Deploy 43445761524 success；current `github-16aed90999ec-43445761524`；health ok/production。
- 生产回执 loader SHA `53095e5f222da3e4c89d61227b9bcca4548629512fa32017b5e0df2258ac963c`；历史成功与当前 paused_by_user 分开；errors/conflicts 空；15候选未提交。
- 备份 `pre-github-16aed90999ec-20261113T151735Z.dump` 校验 OK；受控发布含恢复演练成功；旧数据未改。
- 文档事实 PR #496 合并 main `68b126c628b7b458ec6d002000126afc2e680772`。

## 本批

第一阶段：复用既有 H5 本人登录和 `MembershipCard`，只读展示本人身份/权益、逐卡来源余额快照及核验日期；不迁移数据库、不更新余额、不导入历史消费。

## 工作区

```text
path: /root/hxy-diy-development/member-readonly-20261113
branch: codex/member-readonly-20261113
base/main: 68b126c628b7b458ec6d002000126afc2e680772
```

## 实现

- `GET /api/v1/auth/h5/membership-overview`
  - 仅从本人会话取 user；匿名 401；不接受手机号/user_id 查询。
  - 按 `membership_store_id` 过滤本人来源卡；不返回 source_card_key/完整手机号/卡号/凭据。
  - 年度卡余额 `not_applicable`；储值卡余额只称 `source_snapshot`，`real_time=false`，`split=unverified`，不称本金、不拆本金/赠金、不进入 DIY 钱包。
  - 历史消费和优惠固定 `unverified`、金额 null；不显示假 0。
- `diy-web` 个人中心新增“会员卡与权益”只读区；加载失败不影响原有服务记录/券包；未核实优惠明确显示。
- 无数据库迁移、无后台管理改价、无会员导入。

## 验证

```text
pytest test_customer_membership_overview + h5_auth + membership_verification
27 passed, 9 subtests passed

diy-web build: passed
diy-web tests: 380 tests, 379 passed, 1 skipped
admin build: passed
admin tests: 321 passed
```

额外独立 React 行为：A 加载后切 B 不泄露；B 网络错误可见；重试恢复；换号/关闭后迟到 401 不退出新账号；refresh 重载。

## 合成预览

- 地址：`http://127.0.0.1:4179/`（本机合成 API + 当前构建代码，非生产数据）
- 截图/HTML：`evidence/member-readonly-preview.png`、`evidence/member-readonly-preview.html`
- 储值/年度权益均展示既有周二活动；个人赠礼仅写“以门店记录为准”，不表示已发；来源、字段、只读等内部词不在顾客页堆叠。

## 来源字段

已核对 `C:/.../SOURCE-FIELD-REVIEW.md`：

- 已观察卡类型/余额/赠金/总消费/期限/消费明细/价格方案优惠/券支付/卡金变动。
- 未核验退款/撤销、稳定明细ID、版本、全量历史分页、非零赠金规则、完整手机号归属。
- 本轮只用样本字段做只读展示设计；122 卡数不是冻结快照；15 卡继续暂停。

## 下一阶段（需独立批准）

历史消费账单存储/导入、退款/版本/去重、真实数据批次。
