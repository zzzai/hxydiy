# 会员同步回执四项修复（2026-11-13）

## 状态

- PR #495；合并 `16aed90999ec017114d56bbd2cb87e99e4742576`
- CI 43444886747 success
- Deploy 43445761524 success
- current `github-16aed90999ec-43445761524`
- public health `ok/production`
- loader SHA `53095e5f222da3e4c89d61227b9bcca4548629512fa32017b5e0df2258ac963c`

## 修复

1. 同门店同批次不同事实：整批失效，不保留第一份、不进入 `last_success`/`latest_attempt`；相同内容幂等。
2. 先按 `(store_id,batch_id)` 与门店筛选，再计算本店最近成功提交/来源核验/尝试；无本店回执是 `no_store_receipt`。
3. `last_success` 只取实际成功提交；`no_new` 只更新 `last_verification`；blocked/waiting/protection失败不抹掉历史成功。
4. 旧 blocked 原样保留；`20261113-status-note` 追加原范围授权、用户暂缓、授权时间未记录；note 冲突整批不挂载；展示不是导入授权。
5. 边界：`attempt_at` 优先；无时区未知；JSON 非对象诊断；跨店文件名/批次脱敏；页面 applied 三态。

## 验证

- 定向 19 passed
- 完整后端 1366 passed, 30 skipped, 103 subtests
- admin build + 321 tests
- 真实生产回执只读核验（独立验收）：历史成功/当前暂缓分开，errors/conflicts 空，15候选未提交
- 备份 pre-github-16aed90999ec-20261113T151735Z.dump 校验 OK；受控发布含恢复演练成功

## 边界

无数据库迁移、会员导入、账单导入、15卡恢复、旧数据改写、自动发券/消息。
