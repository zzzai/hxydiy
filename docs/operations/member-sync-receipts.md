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
