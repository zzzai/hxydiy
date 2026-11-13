# 会员同步脱敏回执运维

## 允许读取

只允许读取已识别为脱敏结果的：
- `formal-apply.json`、`preparation-summary.json`、`backup-recovery-result.json`、`bound-attestation.json`
- `BLOCKED-RESULT.json`、`source-verification-summary.json`、`candidate-match-summary.json`

不得读取/复制 `candidate-input.json`、`candidate-phones.txt`、`source-cards.json`、`baseline-private.json` 或任何完整手机号/卡号/余额/凭据。

## 更新流程

1. 人工核对上述脱敏文件的批次、时间、门店、批次 ID 和 SHA。
2. 只在 `hxy-server/app/content/member_sync_receipts/` 增加投影后的脱敏 JSON。
3. 更新 `index.json` 的 allowlist 与 SHA-256。
4. 先跑服务层成功、无新增、阻塞、缺字段、摘要不匹配、重复和冲突测试。
5. 通过正常 PR/CI/发布；不得用文件修改时间代替业务核验时间。

## 展示口径

- 有效来源卡数量：数据库当前事实。
- 上次成功提交：仅显示最近成功/无新增回执。
- 最近尝试：来源检查或同步尝试结果，可为等待登录、基线阻塞或保护校验失败。
- 没有成功回执时保持“待核实”；不能把有历史回执写成“当前已同步”。

## 2026-11-13 修正

- `index.json` 的 `receipts` 和 `status_notes` 都是独立 allowlist；状态说明不能改写旧回执。
- 同门店同批次内容冲突时该批次整体失效，必须人工核对；索引顺序不决定可信结果。
- 先按门店筛选，再计算该店成功/核验/尝试；无本店回执是 `no_store_receipt`，不是全局无数据。
- `no_new` 只更新最近来源核验，不覆盖上次实际成功提交。
- 历史 blocked 原因与当前 `current_processing` 分开显示；2026-11-13 当前状态为“已授权，用户要求暂缓”，授权时间未记录。

## 2026-11-13 边界

- 同一批次的状态说明冲突时，全部 note 不挂载；保留冲突提示，不显示授权/暂停。
- 尝试时间优先使用 `attempt_at`；来源核验和成功提交各用自己的时间，缺失不猜测。
- 校验 JSON 根必须是对象；无时区时间进入未知，不做时区猜测。
