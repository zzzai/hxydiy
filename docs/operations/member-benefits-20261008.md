# 会员权益独立交付

状态：已合并、生产发布和两条计划配置核验通过；真实微信/门店人工买赠未验收。不能合并或运行#218全菜单工具。

## 2026-10-08 生产事实（Asia/Shanghai）

- 顾客#221 HEAD `b0d7c665dd82d0496034c823162c14a4940aacfc`，后台#222 HEAD `44212bd0e5b4636dfb8455da5172e4ca119b761b`；最终主干 `730da016cec3c7935ede3593c370a1f68eb9ac0c`，CI `37715825818`、正式部署 `37716156991` 成功。current `/root/hxy-diy-20260811/releases/github-730da016cec3-37716156991`，MANIFEST与健康通过；运行定价SHA `bd65ff310ec220ae10b4a22daf07eb0ea6078ebedd4e958ba0ee4fbb224b2314`，工具SHA `614e1395dd200f129435812ae15c888976948c2b4215bc49daf0e50cc7f00618`。
- 生产旧annual金额9900、stored金额50000本来正确；实际差异是名称与权益，旧annual周二6.8折/赠89元说明、stored仅退款说明均已替换。原monthly计划行保持不变，但顾客端不再推广。
- 应用前官方备份 `/root/hxy-diy-20260811/backups/daily/daily-20261008T021625Z-25d3bea90921410ab6be19e1.dump`，649239字节，SHA `cc78c6f7ab769c56fb6bd79d85927140326474e994d3c8b91d43072045987c47`，真实隔离恢复通过；复制真实dump至容器 `/tmp/member-plans-preapply-20261008.dump` 并再次核验SHA。
- 新只读预览hash `f7ce09e59b4e3ebc5419da37e209d60434a81dabd275e5ba2c1edf2b260a1cf8`，仅annual/stored两项；显式apply后再预览changed=0。22张卡及余额、2条赠送记录、16项目、66价格、原月卡、充值、订单、612选单与85修订的前后保护摘要全部一致。记录只保留计数/哈希，不输出顾客隐私；没有真实赠送/消费/选单验证写入。
- 公网首页加载 `index-B9tj80LU.js`，公网与安装资源SHA `7d9d590bb0ebb58f8e3fc35acd50e3b0065d72eaa5e1be7496b3ea0ce560b0a8` 一致，含新版两种卡和完整权益文案。正式容器使用合成数据直接调用实际定价函数，年度/储值周二都取普通会员价，不自动6.8折、不自动买赠、无数据库写入；已冻结旧basis兼容由110测试/34子测试及真实HTTP历史重试合同验证。
- 顾客窗口19相关测试及构建、375/390入口→两类详情→返回、完整文案/无溢出/旧推广清除、登录/报告/隐藏功能保护通过；服务器断网隔离110测试34子测试通过，未接生产库。顾客UI证据在 `C:/Users/gaoji/.codex/worktrees/customer-review-five/customer/diy-web/output/playwright/customer-membership-plans-03/`，总控发布/配置/公网证据在总控隔离区 `output/member-benefits-20261008/{deployment,plan-application,public-verification}.json`。UI证据为隔离会话，不冒充真机现场。

范围保持会员only，不包含#218的14项菜单改价；二维码与报告、动态会员码/历史临时隐藏保持。旧seed不是当前计划事实来源，不运行它覆盖配置。买赠配对/补差/续卡/叠加仍未确定，人工赠送须门店确认，不以新宣传文案虚构旧顾客已有赠品。生产已核验项不为记录重复检查或部署。

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
