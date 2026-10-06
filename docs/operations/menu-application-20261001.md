# MENU-20261001 数据应用交接

执行责任：总控在精确提交通过本地/服务器隔离验证、合并及发布后安排。此说明不表示已执行生产应用。禁止用历史seed初始化生产或重新导入会员。

`bootstrap_diy_store` 只在空库填历史fixture，并初始化门店/服务位；不再隐式同步菜单，不覆盖已有项目名称或价格。正式菜单仍需下述受控工具独立应用，不能通过bootstrap绕过鉴权/备份门禁。

## 应用前

核对运行代码精确版本、真实门店ID/code及旧项目引用。完成目标数据库备份、SHA校验和隔离恢复演练。Token、备份、完整预览存仓库外私有目录，不发聊天。使用在职总部目录管理员正常登录Token，放进程环境变量 `HXY_STAFF_TOKEN`，不是 GH_TOKEN，不写参数或日志。

在已核验版本的 `hxy-server/` 目录运行，替换占位值：

```bash
python -m scripts.apply_confirmed_menu --store-id STORE_ID --store-code VERIFIED_STORE_CODE
```

默认只读，返回修改前事实、目标及plan_sha256；核查14项价格/流程/单位与两个旧项目归档。历史 `sync_final_menu` 仅兼容预览，旧无鉴权apply函数拒绝写入。发布代码不会自动修改生产菜单。

## 显式应用

```bash
python -m scripts.apply_confirmed_menu --store-id STORE_ID --store-code VERIFIED_STORE_CODE --apply --expected-plan PREVIEW_SHA256 --backup-file /private/database.dump --backup-sha256 VERIFIED_BACKUP_SHA256
```

漂移拒绝，不自动重跑。成功报告在提交后输出changed/audit_id/project_ids，保存私有证据。再次预览应零修改；核对公开API14项、旧详情/引用、包含服务/整套字段及PriceBook新旧行，检查历史订单保护指纹。数据验证不能代替真机与门店验收。

## 受控补偿

用原报告audit_id预览。应用后有人修改目录或价格则拒绝补偿，重新评审，不覆盖。

```bash
python -m scripts.apply_confirmed_menu --store-id STORE_ID --store-code VERIFIED_STORE_CODE --rollback-audit ORIGINAL_AUDIT_ID
python -m scripts.apply_confirmed_menu --store-id STORE_ID --store-code VERIFIED_STORE_CODE --rollback-audit ORIGINAL_AUDIT_ID --apply --expected-plan COMPENSATION_PREVIEW_SHA256 --backup-file /private/fresh-database.dump --backup-sha256 VERIFIED_FRESH_BACKUP_SHA256
```

补偿追加价格、恢复旧字段，保留审计；新建项目归档，不删除。确认金额/历史订单不回写。补偿重复预览零改动。提交结果不明先核对审计/状态，不盲目换预览重写；全库灾难恢复另沿已验证备份流程评估。
