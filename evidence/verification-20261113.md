# 四处回执修复：验证证据

- 时间：2026-11-13 22:20–22:32 Asia/Shanghai
- 工作区：`/root/hxy-diy-development/coupon-acceptance-20261113`
- 分支：`codex/coupon-acceptance-20261113`
- 基线：`49f7f05aec389f2b95b788c515a78a2fe3efaa85`（最新 main）
- 状态文件：`STATUS.md` / `STATUS.json`
- dirty patch SHA：见 `STATUS.json.dirty_patch_sha256`

## 定向合同测试

```text
cd hxy-server
/root/hxy-diy-development/.venv-admin-coupon/bin/python -m pytest -q tests/test_coupon_admin_contract.py
```

结果：`19 passed, 1 warning`，退出码 0。

覆盖：冲突回执不可信、顺序无关、门店隔离、no_new 不覆盖 last_success、历史 blocked/current_processing 分离、note 冲突、attempt_at 优先级、无时区/非法 JSON 边界、路由级输出。

## 完整后端

```text
cd hxy-server
/root/hxy-diy-development/.venv-admin-coupon/bin/python -m pytest -q --ignore=tests/test_admin_catalog_schemathesis.py
```

结果：`1366 passed, 30 skipped, 14 warnings, 103 subtests passed`，退出码 0。

## Admin

```text
cd admin-react
npm run build
npx -y node@22 --experimental-strip-types --test tests/*.test.ts
```

结果：build 成功；前端测试 `321 passed`，退出码 0。

## 未执行

- 未跑生产数据/会员导入
- 未做备份恢复或发布（待提交/PR/CI 后）
- 未把合成测试当真实门店或 Excel/WPS 验收
