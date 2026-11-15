# 来源消费历史与余额核验契约

状态：四张独立消费/余额表已按 2026-11-14 授权创建并发布；顾客只读接口已存在。2026-11-15 正在独立工作区验证后台采集与追加导入；尚未导入真实消费或余额快照。新卡同步为独立已完成任务，不得重放其批次。
范围：`source=meiguanjia_export`，来源租户 1581452 / 来源门店 1581453 -> DIY 门店 1；store_code `hxy-anyang-ziwei-001`。

## 1. 已核实与未核实

已从正常登录页面只读核实（见 `SOURCE-FIELD-REVIEW.md`）：

- 卡查询：卡类型、总额、余额、赠金、总消费、总充值、开卡/到期/最后消费、门店。
- 消费记录：单号、时间、消费信息、金额、门店；类型含服务/开卡/套餐/充值。
- 单据详情：逐项数量/原价/成交额、支付构成、消费总额、入账、价格方案优惠、优惠券、卡金。
- 卡金变动：单号、类型、卡金/赠金变动与余额、时间、门店；按单号可关联。
- 年度卡卡内总消费可为零但仍有顾客消费记录；开卡商品行可为零而整单实收99。
- 一张账单可含多人服务。
- 2026-11-14 营业流水样本：同一业务单号可出现4次“已撤单（已重录）”，原价/成交/入账/付款金额仍为正数；也有同号在“反结算”筛选下当前行仍为“正常单（已结账）”。撤单表示历史版本，不能因金额正数或筛选命中当成有效消费/退款。
- 当前正常单结账时间可早于历史撤单操作时间；不能按最大时间或列表顺序选当前版本。必须由来源显式当前状态/版本规则判定。
- 时间筛选只有下单/结账，没有更新时间/撤单时间；最近结账窗口不能宣称不漏迟到修改。
- 收款流水有交易号/支付状态/关联流水/退款人/退款时间等字段，但有限日期无退款成功样例；撤单/重结算不等同支付渠道退款，不能推部分退款分摊。

尚未核实的映射不得猜测：退款/部分退款关联与分摊、明细稳定 ID、账单修订版本顺序、历史时间覆盖、非零赠金权益规则。2026-11-15 后台只读首轮已完整读取 126 卡/9页、124 位顾客/356 条个人消费记录；126 个原始卡号与完整手机号均唯一匹配 DIY 当前归属。个人消费记录分页完整不代表退款、历史修订及时间覆盖已完整。收款流水找到一笔退款成功样例，但关联流水为空，不能分配给会员账单。

## 2. 已批准的独立结构

以下四组表已存在；结构事实以 `20261114_member_consumption.py` 及当前模型为准。后续导入仅追加新事实，不修改受审新增卡导入器，不写 DIY `orders/recharges/user_coupons` 或旧 `membership_cards.balance_cents`。

### 2.1 `membership_consumption_batches`

```sql
id BIGSERIAL PRIMARY KEY,
source VARCHAR(32) NOT NULL,              -- meiguanjia_export
store_id INTEGER NOT NULL REFERENCES stores(id),
batch_key VARCHAR(64) NOT NULL,           -- operator-defined exact batch
source_snapshot_sha256 CHAR(64) NOT NULL,
manifest_sha256 CHAR(64) NOT NULL,
query_range_start TIMESTAMPTZ NOT NULL,   -- declared source query range
query_range_end TIMESTAMPTZ NOT NULL,
page_count INTEGER NULL,
last_page_complete BOOLEAN NULL,
coverage_gaps JSON NULL,                 -- explicit missing ranges/pages
observed_at TIMESTAMPTZ NOT NULL,         -- actual read time
status VARCHAR(16) NOT NULL,              -- preview/applied/blocked
evidence_ref TEXT NOT NULL,               -- private redacted evidence ref, no PII
created_by INTEGER NULL REFERENCES staff(id),
created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
UNIQUE(source, store_id, batch_key)
```

### 2.2 `membership_consumption_bills`

```sql
id BIGSERIAL PRIMARY KEY,
batch_id BIGINT NOT NULL REFERENCES membership_consumption_batches(id),
source VARCHAR(32) NOT NULL,
store_id INTEGER NOT NULL REFERENCES stores(id),
source_bill_no VARCHAR(128) NOT NULL,
source_bill_version VARCHAR(64) NULL,     -- only if source proves it
bill_type VARCHAR(16) NOT NULL DEFAULT 'unknown',  -- service/open_card/recharge/unknown
bill_status VARCHAR(24) NOT NULL DEFAULT 'unknown', -- normal_settled/voided/reversed/unknown; source-explicit only
source_version_no INTEGER NULL,                    -- only if source proves revision order
source_current_marker VARCHAR(32) NULL,            -- source-explicit current marker, if any
occurred_at TIMESTAMPTZ NOT NULL,         -- source local time -> explicit offset
settled_at TIMESTAMPTZ NULL,
currency CHAR(3) NOT NULL DEFAULT 'CNY',
store_price_total_cents BIGINT NULL,
settled_total_cents BIGINT NULL,          -- final consumption amount, includes coupon payment
payment_evidence_complete BOOLEAN NOT NULL DEFAULT FALSE,
price_plan_discount_cents BIGINT NULL,
coupon_payment_cents BIGINT NULL,
card_principal_debit_cents BIGINT NULL,
card_bonus_debit_cents BIGINT NULL,
cash_payment_cents BIGINT NULL,
other_payment_cents BIGINT NULL,
card_id BIGINT NULL REFERENCES membership_cards(id),
user_id INTEGER NULL REFERENCES users(id),
attribution_status VARCHAR(24) NOT NULL DEFAULT 'unresolved',  -- owned/shared/unresolved
refund_status VARCHAR(16) NOT NULL DEFAULT 'unknown',          -- none/partial/refunded/void/unknown
original_bill_id BIGINT NULL REFERENCES membership_consumption_bills(id),
source_row_sha256 CHAR(64) NOT NULL,
content_sha256 CHAR(64) NOT NULL,
raw_evidence_ref TEXT NOT NULL,
created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
UNIQUE(source, store_id, source_bill_no, content_sha256)
```

账单头与行不可重复累计；行只存在此账单版本下。

### 2.3 `membership_consumption_lines`

```sql
id BIGSERIAL PRIMARY KEY,
bill_id BIGINT NOT NULL REFERENCES membership_consumption_bills(id),
source_line_key VARCHAR(128) NULL,        -- only when source proves stable
line_order INTEGER NOT NULL,
description TEXT NOT NULL,
quantity INTEGER NULL,
store_price_cents BIGINT NULL,
settled_cents BIGINT NULL,
payment_breakdown_json JSON NULL,
line_sha256 CHAR(64) NOT NULL
-- no UNIQUE(bill_id,line_sha256): two legitimate identical service lines may exist.
-- There is no stable line business key until source proves one; keep the whole
-- bill's ordered line multiset and compare whole-bill version hashes.
```

行号不稳定时：**不把 line_order 当业务主键**，整单按 `source_row_sha256` 保存版本；后续同一单号内容变化生成新账单版本/修订，不覆盖旧证据。

### 2.4 `membership_balance_snapshots`

```sql
id BIGSERIAL PRIMARY KEY,
card_id BIGINT NOT NULL REFERENCES membership_cards(id),
source VARCHAR(32) NOT NULL,
store_id INTEGER NOT NULL REFERENCES stores(id),
observed_at TIMESTAMPTZ NOT NULL,
principal_cents BIGINT NULL,
bonus_cents BIGINT NULL,
total_cents BIGINT NULL,
source_batch_id BIGINT NOT NULL REFERENCES membership_consumption_batches(id),
evidence_ref TEXT NOT NULL,
created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
UNIQUE(card_id, observed_at, source_batch_id)
-- source_batch_id is NOT NULL so NULL does not defeat uniqueness.
-- If an ad-hoc observation without batch is later required, use a separate
-- partial unique index on (card_id, observed_at) WHERE source_batch_id IS NULL.
```

只有来源明确本金/赠金时才拆；只有总余额时 `principal_cents=NULL, bonus_cents=NULL, total_cents=...`，不得把总余额当本金；未知为 NULL，不为0。余额持续核验保存新快照；仍然不是 DIY 钱包。

### 2.5 退款/冲正/收款流水（先不建表直到字段核实）

营业账单的撤单/反结算和收款流水退款是两套证据：撤单/重结算不等于支付渠道退款；收款流水有交易号/支付状态/退款时间/关联流水，但本次有限区间无退款成功样例。建议只有在拿到原单号、原支付交易、原明细/分摊、状态和金额证据后，再增加 `membership_consumption_adjustments`/`payment_transactions`。在此之前：

- `bill_status != normal_settled` 或退款状态=unknown 的账单不计入累计优惠；
- 已撤单旧版本保留但排除；正数金额不改变排除；
- 不通过修改旧账单静默冲销；
- 保留已核实账单，显示“退款/撤单待核实”；
- 无退款成功样例，不实现部分退款金额/分摊算法，不猜支付退款关系。

## 3. 主键、幂等与版本

- 批次键：`(source, store_id, batch_key)`；批次 SHA 绑定来源快照和 manifest。
- 账单头业务键：`(source, store_id, source_bill_no, content_sha256)`（规范化语义摘要，非证据行 SHA）；只有来源证明单号全租户唯一且版本规则后，才可升级 `source_bill_version` 唯一约束。
- 相同内容重放：整批/逐单零新增。
- 相同单号内容变化：新 `source_row_sha256`/版本，旧记录保留；**在来源证明版本顺序/当前版本规则前，整组账单冲突，全部排除并标异常，不做 first-wins，也不依赖输入顺序**。
- 行：只有来源证明稳定明细ID才使用 `source_line_key`；否则整单版本保存，`line_order` 仅展示，不参与去重。
- 跨账户/跨店：`store_id` 和 owner 必须严格匹配；未知归属进入 `unresolved`，不展示为本人。

## 4. 同人多卡、多人账单去重

- 账单以单号只累计一次；账单下的多行不按卡重复。
- 多卡同人：只累加一次账单；权益并集只决定会员价/权益，不重复计优惠。
- 多人账单：保留账单和可核实项目；只有明确本人行/归属时才计入个人“消费历史”；否则标记 shared/unresolved，不作为个人服务或健康画像。
- 卡金变动以业务单号关联账单；不能把同一笔卡金变动重复作为消费。
- 跨来源同一笔消费无可靠关联时不合并、不去重成“全渠道总额”；分开呈现。

## 5. 与既有 DIY 指标边界

服务器现有 `docs/contracts/customer-account-profile.md` 第6节的“累计会员节省”来自 DIY 已完成服务的门店价/会员价快照差，不能把本次来源价格方案优惠无依据塞进旧指标。新指标独立命名“来源消费优惠/累计消费优惠”，并明确数据源、覆盖期和缺失；不改写 DIY 订单、钱包、价格或旧统计。

## 6. 金额与节省口径

只对 `bill_type=service` 且 `attribution_status=owned`、原价/成交/支付完整、`refund_status=none` 的账单计算：

```text
bill_savings_cents = store_price_total_cents - settled_total_cents
```

规则：

- `settled_total_cents` 是最终消费结算额，包含储值扣款、现金、其他真实支付和优惠券支付；不是“现金实付”。
- 必须显式 `payment_evidence_complete=true`，且本金/赠金/券/现金/其他每个组成部分都不是 NULL；五项合计必须等于 `settled_total_cents`，否则 unknown/anomaly，禁止用 `or 0` 补齐。
- `settled_total_cents < 0`、支付合计不一致、原价合计<成交、行/头不一致均为 anomaly；不得计算为优惠。
- 储值扣款是支付，不是免费；不能把储值支付额当优惠。
- 价格方案优惠单独存；优惠券支付单独存；**券支付不自动记为会员节省**，因为券来源/购券成本未知。
- 例：原价300、成交240、卡金150、券90 -> 节省60；不是150，也不是240。
- 例：119原价、79储值、现金0 -> 节省40；不是119。
- 充值、开卡、购套餐不算消费优惠；开卡行0而整单99只作为开卡费，不参与节省。
- 年卡费单列，不计算回本；赠金/赠礼不重复计入。
- 负差额或行/头合计不一致：进入核对异常，不静默取0，不纳入已核验优惠。
- 缺原价/数量/支付构成：保留账单，`savings_cents=NULL`，不计入累计，文案“已核验记录累计优惠”并注明覆盖范围。
- 统计覆盖期不能只用已核实账单最小/最大 occurred_at；必须使用批次声明的 `query_range_start/end`、分页完整性、最后页和 `coverage_gaps`。账单日期范围只是结果范围，不是采集覆盖期。
- 来源时间筛选只有下单/结账，没有更新/撤单时间；只按最近结账窗口采集不能证明迟到撤单/重结算不漏，必须明确“覆盖不完整/待增量核验”。
- 多笔退款/部分退款：按原账单和可核对分摊调整；缺分摊阻断该账单，不按实付退款简单反推。

## 7. 合成验收矩阵

| 样例 | 期望 |
|---|---|
| 原价300/成交240/卡金150/券90 | 节省60；券支付90单列；卡金支付不算免费 |
| 原价119/储值79/现金0 | 节省40，不是119 |
| 支付拆分全 None / 只知1分而成交240 | unknown/anomaly，不计算 |
| 成交-1000 | anomaly，不计算 |
| 同一批次重复导入两次 | 第二次零新增；唯一键幂等 |
| 同单号v1有效/v2退款unknown，正序/逆序 | 整组冲突，savings=null，verified=0，blocked/conflict各1；顺序无关 |
| 多人账单含2人项目 | 账单只累计一次；未归属行不计入个人；不推断健康画像 |
| 同人多卡关联同一账单 | 账单只累计一次；权益并集不影响账单金额 |
| 退款未知 | 账单不计入节省，状态“退款待核实” |
| 只有充值/开卡/套餐 | 不进入消费优惠；开卡费单列 |
| 缺原价或支付拆分 | 节省NULL，显示未核实；不填0 |
| 跨账户/跨店读取 | 403/404，不返回账单；店长只本店 |
| 行/头合计不一致 | 核对异常，不静默取0 |
| 完全相同的两条合法服务行 | 保留有序多重集，不按内容去重 |
| 无已核验账单 | 累计savings=null，不是0 |
| 同单4个已撤单版本+当前正常单无显式当前标记 | 整组冲突，不按时间/顺序选当前 |
| 已撤单金额仍为正数 | blocked，不计入消费/优惠 |
| 收款退款无成功样例/无分摊 | 不计算部分退款，标待核实 |
| 只有下单/结账筛选 | 覆盖不完整；不能用窗口声称全量 |
| 北京时间边界 | 明确来源本地时间+offsets；展示按明确时区 |

## 8. 试运行、备份、恢复、回滚与审批

### 仅迁移（不含真实数据）

1. 生成 Alembic revision；只新增表/索引/约束，不改旧字段、不写业务行。
2. 隔离 PostgreSQL 建库；`upgrade head` + `downgrade -1` + 再 `upgrade`；校验表/约束存在。
3. 备份生产 pre-migration `pg_dump`，SHA/大小记录；隔离恢复演练；生产只执行 up。
4. 迁移前后旧表行数、关键金额汇总、审计数不变；无业务写入。
5. 回滚：应用回退上一 release；若需降级数据库，先停写、确认新表为空、按预演 `downgrade`；旧表不动。

### 真实历史导入（另批精确批准）

1. 绑定冻结来源快照 SHA、门店/租户、日期分页完整凭证。
2. 预览：逐单候选、类型、归属、支付拆分、退款未知、去重、预计新增/异常；不写。
3. 备份 + 隔离恢复；确认当前表行数和审计基线。
4. 精确批准表名/迁移版本/批次/预计新增数；按批次事务导入；同批重放零新增。
5. 导入后只读核对：旧 DIY 订单/钱包/卡/价/审计不变；外部账单不进入 DIY 营收。
6. 真实导入/余额更新/15卡恢复均不在本方案授权内。

## 9. 当前结论（2026-11-14 实现后）

- 本分支已实现纯领域模型 + Alembic 迁移草案 + SQLAlchemy 模型 + 本人只读 API + 前端组件与行为测试；**未执行生产迁移、未写生产数据、未导入历史、未更新余额、未恢复15卡、未部署**。
- 语义完整性：`bill_content_sha256` 现纳入精确 `Decimal` 数量、`occurred_at`/`settled_at`、`source_version_no`/`source_current_marker`；持久化摘要与重算不一致即整组隔离（不展示被篡改事实），合法新算未知证据仍可见。冲突先按本人候选单号取整组跨归属判定，不泄漏他人组数/明细。
- 覆盖口径：完整性按已生效批次声明的分页、日期区间与缺失声明保守判定；区间不连续或声明缺失即“覆盖不完整”，原始缺失文本不进入公开响应。
- 余额只读投影：拒绝负数、本金+赠金≠总额、同刻原始卡事实与观测不一致；最新 0 对旧 active 卡给出仅展示对账态 `zero_balance_against_active_card_review`，不改权益/身份；卡事实时间与最新观测时间分离。
- 前端：来源金额精确分/币种感知（1499 => ¥14.99，非 CNY 不用 ¥）；加载更多同步在途闸、按服务端 offset 推进、按账单 ID 去重、旧账号迟到响应隔离；空值显示“未核实”而非 0。
- 迁移验收（隔离一次性 PostgreSQL，非生产）：无四表基线 `stamp 20261112_coupon_poster_links` → `upgrade head` 建四表+约束/索引且旧基线行不变 → 空表 `downgrade` → 再 `upgrade` → 非空表 `downgrade` 拒绝且行保留。脚本 `hxy-server/scripts/verify_member_consumption_upgrade.py`。
- 测试：后端消费/余额/迁移契约相关测试通过；独立探针 `codex-api-review-v2.py` 12/12、`codex-balance-review.py` 10/10 通过；前端 hook+组件测试通过；`tsc -b` 与 `vite build` 通过。
- 仍需先确认退款/撤销字段、稳定账单/明细标识、全量历史分页和逐人归属；未确认部分保持 unknown/阻断。真实数据接入不在本分支授权内。
- 人工门店19项、Excel/WPS、真实来源核对继续待人工。


## 2026-11-15 后台采集与追加导入开发边界

- 专用 Chrome 通过本机 Playwright 私有管道访问正常页面控件；不操作系统鼠标键盘，不读取或导出浏览器凭据、Cookie、storage state、网络载荷或照片。
- `financial_collector.py` 仅生成仓库外受限的来源观察，未接通生产写入。每卡核对原始卡号、完整手机号、门店；每人读取消费记录完整分页与对应账单详情。未知状态和金额保留未知。
- 营业流水含分组表头及虚拟滚动。按表头列标识读取，分页总数、实际行数、末页、状态和门店均须核对；不能把当前渲染的少量虚拟行当作完整页。只保留本批会员账单匹配所需字段。
- 来源中开卡行可显示零元，整单实收仍为开卡费；附赠券可能显示 `原价¥` 而无数字。数量或价格缺失保留 `null`，不得填 1/0，不得将开卡/充值/套餐购买当服务优惠。
- `member_financial_import.py` 为未接通生产入口的事务服务。标准化数据的全部字段绑定 manifest SHA；卡归属由原始卡号哈希和完整手机号重新核对，不接受调用方传入 DIY user/card ID。
- 相同批次重放零新增；同号不同账单版本仅追加新版本，顾客投影继续按冲突组屏蔽，禁止覆盖旧版本。相同卡同一观察时间的不同余额停写；本金/赠金拆分未知时保持 `null`。
- PostgreSQL 导入以事务 advisory lock 串行化；失败整批回滚。真实写入前仍需精确输入、当前只读保护基准、真实备份与隔离恢复、批准回执以及提交后的旧资料保护和重复预览验收。
- 本契约更新不构成真实历史已同步、自动任务已启用或应用已再次发布的证明。


## 2026-11-15 本批只读核验与受控入口

- 正常后台页面双轮读取均为 126 卡、124 位顾客、356 条个人消费记录；列表余额/卡片余额相同，完整手机号和原始卡号匹配现有 DIY 归属。
- 营业流水 118 页共 1173 行，356 个会员业务单号全部匹配；6 个单号存在撤单重录版本。收款流水 20 页共 291 行，96 条成功支付匹配会员单号，1 条退款成功记录没有关联单号。
- 当前精确候选为 101 笔单人、单卡归属、无版本冲突的服务账单和 47 张储值卡余额快照。多人、归属不明确、多卡无法证明单据用卡、修订冲突不挂到个人名下。开卡/充值等不算服务优惠。
- 本批退款和完整支付分摊尚未证明，所有累计消费优惠保持 null/未核实；结算金额只表示来源账单记录，不宣称退款后净支出。余额本金未知，赠金观测为零，不把旧卡余额改成新快照。
- `finance_packet.py` 在两个完整来源观察一致后，按真实单据标题、门店、数量和金额交叉核对编译候选；原始证据和精确输入均绑定 SHA。
- `finance_controlled.py` 仅供总控使用：冻结全库行摘要、只读预览、真实 pg_dump、独立库恢复逐表核对、真实输入隔离应用与重复预览，再由精确 manifest 执行一次生产事务。应用事务短时持有 SHARE 表锁，提交前核对所有旧表和旧财务行不变、四表增量准确；失败回滚。
- 本批正常导入只增加独立消费四表中的事实，复用已上线顾客只读接口，不更改会员卡、用户、钱包、订单、价格、权限或结构。脚本及测试完成不代表生产已经导入，以批次 PRODUCTION-RESULT 为准。

- 首次隔离恢复中发现整数 Decimal 数量与顾客查询整数表示的内容哈希不一致，101 笔被隐藏；生产零写入。已补真实持久化回归，并在新导入器内规范化整数量值；不更改已上线哈希规则或任何旧行。修复后沿用同一业务批次键/输入，使用独立运行目录保留原失败证据，再完成完整恢复演练。
