# 会员权益独立交付

状态：开发验证，生产由总控唯一执行。不能合并或运行#218全菜单工具。

## 范围和依据

复用已确认2026-10-07两图的会员计划内容，仅annual/stored：年度99元一年、储值500元余额耗尽失效；两类会员价、周二按门店价任意主项买一赠一、开卡赠≤99元项目一次，储值另赠29.9元养生茶一盒。主项配对/补差/续卡/叠加不猜，门店人工受控确认，不自动免单。文案更新不产生实际赠送、支付、充值或消费。

保留monthly的数据库记录/状态、22张旧卡、余额、所有赠送记录、已冻结价格、14项菜单价格、动态码及既有组合赠泡规则。顾客窗口仅修改前端推广展示，共享合同由管理后台窗口唯一维护。

## 最小实现与验收

- `membership_pricing.confirmed_price_for_line` 取消新确认自动周二6.8折，继续验证时区、年度到期、动态核验、本店多卡权益；旧basis枚举保留以兼容冻结历史。普通会员确认价不代替人工周二买赠结算。
- `reconcile_member_plans_20261008` 只同步两个已发布计划的name/price_cents/benefits，不修改status。默认只读，无计划缺失补建；全计划基线和差异加入preview_hash，状态或其他计划变更也拒绝旧预览。apply只锁member_plans后验证哈希，同事务更新并追加一条审计，重复零写入。
- 本地与服务器断网隔离运行计划、周二确认、历史冻结、加选、多卡和门店隔离合同测试。计划保护测试使用22张合成卡，并对monthly/个人卡/赠送/订单/充值/项目/价格前后快照比较，不使用生产写探针。

## 总控生产步骤

1. 合并本会员only后端PR与顾客窗口的独立前端PR；精确主干CI通过后正式部署、核验current/MANIFEST和入口健康。不要纳入#218。
2. 官方真实备份、SHA256和隔离恢复演练通过。将真实dump挂载/复制到执行容器可读的临时位置，不使用非空证明替代备份。
3. 完整提供同版本scripts/app环境，在当前API环境默认只读预览；应仅annual/stored两个计划，不打印环境变量。保留预览及保护证据。
4. 显式apply必须提供刚核验的preview_hash和真实dump SHA，锁等待5秒、语句30秒；漂移拒绝，不自动重试。再预览changed=0，核对monthly、22卡/余额/赠送、菜单价格及历史冻结保护不变。
5. 验证前端只推广两类及相同金额/说明；新周二确认使用普通会员价、不自动买赠。真实服务/人工赠送验收交人，不造生产测试订单。

```sh
PYTHONPATH=/app python -m scripts.reconcile_member_plans_20261008
PYTHONPATH=/app python -m scripts.reconcile_member_plans_20261008 --apply \
  --expected-hash <fresh_preview_hash> \
  --backup-reference <actual_dump_path> --backup-sha256 <verified_sha256>
PYTHONPATH=/app python -m scripts.reconcile_member_plans_20261008
```

事务失败整体回滚，应用成功后不自动恢复整库覆盖后续业务；需要逆向计划更正时由总控确认固定旧值并重新受控预览。无新增迁移，不导入会员，不触碰菜单价格，不补发历史赠送。生产完成由总控更新CURRENT-STATE/WORK-STATUS。
