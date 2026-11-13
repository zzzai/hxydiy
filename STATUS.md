# HXY 会员同步与运营后台 STATUS

更新时间：2026-11-13 22:32 Asia/Shanghai
执行方：DeepSeek Harness
控制/独立审查：Codex

## 批次

| 批次 | 状态 | 说明 |
|---|---|---|
| A 四处回执修复 + 边界修正 | dirty 已验证，待提交/PR/CI/发布 | 见 `evidence/verification-20261113.md` |
| B 会员消费/余额/优惠 | 来源字段未核实，未开发真实导入 | 见 `docs/contracts/member-card-entitlements.md` |
| C 数据库/历史导入 | 未开始 | 15卡继续暂停；不自动恢复 |
| D 后台信息架构 | 未开始 | 复用已有页面 |

## A 最新验证

```text
基线：49f7f05aec389f2b95b788c515a78a2fe3efaa85（latest main）
分支：codex/coupon-acceptance-20261113
定向合同：19 passed, 1 warning
完整后端：1366 passed, 30 skipped, 103 subtests passed
Admin build：通过（tsc -b + vite build）
Admin tests：321 passed
dirty patch SHA：见 STATUS.json
```

已覆盖：

- 冲突回执批次整体失效、顺序无关
- note 冲突整批不挂载，不输出授权/暂停
- 先门店隔离再聚合；无本店回执 `no_store_receipt`
- `no_new` 只更新 `last_verification`，不覆盖 `last_success`
- 历史 blocked 与 `current_processing` 分离
- `attempt_at` 优先；未知/混合时区不猜、不崩溃
- 页面 applied 三态，未知显示“未记录”
- 跨店冲突/错误/文件名不泄漏

## 基线

```text
worktree: /root/hxy-diy-development/coupon-acceptance-20261113
branch: codex/coupon-acceptance-20261113
HEAD/base: 49f7f05aec389f2b95b788c515a78a2fe3efaa85
last known production: github-28d85bbea723-43412883940
last known app SHA: 28d85bbea72382e415664a0712b353bb32b26736
```

SSH/HTTP 已恢复；生产发布前会重新核对 current/health。

## 未执行/保护

未执行：会员导入、历史账单导入、15卡恢复、数据库迁移、旧数据改写、自动发券/消息、服务器清理、凭据读取。未把合成测试当真实门店/Excel 验收。

## 下一步

1. 提交四处修复及文档、STATUS/evidence。
2. 推送、PR、正常 CI/Trusted PR Gate。
3. 备份恢复、生产发布、只读终验。
4. 从最新 main 建会员独立工作区；核实来源字段与 facts 入口；真实导入另批批准。
