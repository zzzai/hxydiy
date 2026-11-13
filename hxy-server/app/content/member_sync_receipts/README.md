# 会员同步脱敏回执（服务端内容）

本目录只保存从已识别为脱敏结果的会员同步回执中人工投影出的 allowlist 字段。
不包含原始会员输入、完整手机号、卡号、余额明细、凭据或会话密钥。

## 来源

- 上次成功批次：`MEMBER-SYNC-ZHB-20261106-3CARDS`
  - 原始脱敏证据：服务器私有 `member-sync-zhb-20261106/batch-20261106-3cards/formal-apply.json`
  - 备份恢复：同目录 `backup-recovery-result.json`
  - 来源确认：同目录 `bound-attestation.json`
- 最近尝试：`MEMBER-SYNC-ZHB-20261113-READONLY`
  - 原始脱敏证据：服务器私有 `member-sync-zhb-20261113/run-readonly/BLOCKED-RESULT.json`

## 校验

`index.json` 是唯一 allowlist；每个文件的 SHA-256 在加载时与索引比对。
SHA 仅证明内容完整性，不单独证明来源真实性。相同批次不同内容会在加载层报冲突，不覆盖旧回执。
