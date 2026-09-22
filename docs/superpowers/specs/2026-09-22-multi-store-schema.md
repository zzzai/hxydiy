# 多店 store_id 架构 Schema 设计

## 1. 基本信息

- Feature ID：`MULTI-STORE-005`
- 当前状态：`Spec Draft`（待评审）
- 编制：WorkBuddy（hxy-diy 总控线），2026-09-22
- 依赖：`BRAND-ACCESS-003` 账号授权底座（已交付于 `wb-migration-integration`，HEAD `0bf0444`）；`BRAND-CATALOG-004` 项目价格分层（`Spec Ready`，见 `2026-09-21-chain-brand-access-and-catalog-design.md`）
- 迁移父点：`20260921_staff_scope`（迁移图单头，线性）
- 业务期限：门店 2 计划 2026-09 末开业

## 2. 现状盘点（实测证据，2026-09-22）

### 2.1 已就绪

| 层 | 证据 |
|---|---|
| 门店主数据 | `stores`：store_code 全局唯一、status 生命周期（preparing/open/closed）、城市/地址/营业时间/经纬度 |
| 空间资源 | `rooms.store_id` FK 就位，空间层级（20260820_store_space_hierarchy）就位；门店 1 的 17 服务位（8 沙发 + 9 床位）即按此建模 |
| 数据隔离 | 20260825/26 系列迁移已完成 audit/event/scrm/membership/tag/coupon/staff/profile 的 store 作用域；20 个模型文件含 store_id |
| 授权底座 | `staff_scope_assignments`：brand_admin/hq_operator/store_manager/store_staff × brand/store 作用域，含角色-作用域一致性检查约束与部分唯一索引（PR130） |
| 内容作用域 | `page_contents` 唯一约束为 (store_id, page_key)，多店内容天然隔离 |
| 目录版本 | catalog_options 经 project_id 继承门店作用域；项目/商品/加项 code 全局唯一（与总部模板模型兼容） |

### 2.2 全局设计（确认无需门店作用域）

- `users`、客户身份（identity / external_identity / customer_profile*）：顾客是品牌级资产，跨店识别
- `browser`（浏览器实例）：基础设施
- `staff_scope_assignments`：授权表本身即作用域载体

### 2.3 缺口清单

| # | 缺口 | 层级 | 定性 |
|---|---|---|---|
| G1 | `rooms.code` 全局唯一，门店 2 开房时编码碰撞风险 | schema | 决策点（见 5.1） |
| G2 | `BRAND-CATALOG-004` 未实施：总部项目模板 + 价格政策 + 门店覆盖三层结构缺表 | schema | 本设计核心（见 4） |
| G3 | 代码路径单店假设：公开目录默认门店、DIY 内容/QR 入店绑定、admin 默认 store_id=1 | 代码 | 盘点任务（见 6 PR3） |
| G4 | 门店 2 供给：rooms/服务位/QR/页面内容/价格簿种子数据 | 数据 | 供给迁移（见 5.2） |
| G5 | 会员权益跨店规则：membership_store_scope 已按店隔离，品牌级通用还是门店限定 | 业务 | 未决（见 8） |

## 3. 目标与非目标

### 3.1 目标

- 补齐 G2 三层目录价格 schema，落地 `BRAND-CATALOG-004` 已冻结语义（总部模板 + 门店实例 + 价格解析优先级）
- 给出 G1/G4 的明确处置方案，支撑门店 2 按期开业
- 全部新迁移以 `20260921_staff_scope` 为父，保持迁移图单头线性
- 迁移不改变门店 1 的公开项目、价格与历史引用（对齐既有 spec §9.2）

### 3.2 非目标

- 不改变顾客端下单、支付、库存、采购或履约范围
- 不重写历史订单、选单、版本化目录的引用
- 不引入区域经理角色、SSO 或外部身份提供方
- 门店物理资源操作（开房/派单/请假/清洁/释放）仍归第三方「智慧宝」，不在本设计

## 4. 数据模型（G2：总部目录与价格分层）

### 4.1 总部项目模板 `project_templates`

| 列 | 类型 | 说明 |
|---|---|---|
| id | int PK | |
| code | varchar(32) unique | 品牌全局唯一，与既有项目编码同规则 |
| name / category / duration_min | 既有规则 | 品牌主数据，仅总部可改 |
| desc / image_url / detail_modules / tags | text/json | 详情模块受控类型沿用现有校验 |
| display_order | int | 品牌级展示顺序 |
| brand_enabled | bool | 品牌启停；停用后全部门店不得上架（spec §5.3） |
| created_by / created_at / updated_at | | 审计 |

### 4.2 价格政策 `template_price_policies`

| 列 | 说明 |
|---|---|
| id / template_id FK | |
| price_type | `store / member / group`（门店价/会员价/团购价，对齐 spec §5.2） |
| standard_price_cents | 总部标准价 |
| override_allowed | 是否允许门店覆盖 |
| min_price_cents / max_price_cents | 可空，覆盖合法区间 |
| force_standard | 强制总部价 |
| 唯一约束 | (template_id, price_type) |

### 4.3 门店实例关联与覆盖

- `projects` 新增 `template_id`（可空 FK → project_templates）：既有 14 个门店项目迁移期回填关联，**项目 ID、历史引用、上下架状态不变**。
- 门店覆盖价 `store_price_overrides`：(project_id, price_type) 唯一，列：override_price_cents、updated_by、updated_at。服务端按 spec §5.2 解析有效价：force_standard → 标准价；允许覆盖且本店值合法 → 覆盖价；否则标准价。
- 会员价开关（catalog-closure 退役时识别的候选 backlog）若立项，落在 template_price_policies 增列，**不**单独建表。

### 4.4 与既有模型的关系

- `price_books`（20260828_price_book_effective_to 已带有效期）继续服务会员定价快照；模板标准价为定价输入之一，不替换 price_book 机制。
- catalog_options 的版本化选项继续挂在门店 project 上；模板层的选项模板化列入后续迭代，首期不做。

## 5. 迁移设计

### 5.1 G1：rooms.code 唯一性

- **采用**：保持全局唯一 + 编码规范 `{store_code}-{seq}`（如 `Z1-R01`），门店 2 供给数据按规范生成。
- **不采用**：放松为 (store_id, code) 复合唯一——需重写约束并影响 QR 内容、智慧宝对接与既有报表口径，风险大于收益。
- QR 码内容与服务位标识因此保持品牌全局唯一，跨店不歧义。

### 5.2 G4：门店 2 供给迁移（数据迁移，与 schema 迁移分离）

- 单独迁移文件，仅 INSERT：`stores`（门店 2 主数据，status=preparing）→ `rooms`（房间/沙发/床位，编码按 5.1 规范）→ 服务位 QR 记录 → `page_contents` 门店 2 页面 → 价格簿初始行。
- 供给参数（店名、编码、房间数）以迁移内的显式常量声明，禁止运行时探测。
- 与 schema 迁移分文件、分许可：schema 迁移先进隔离演练，供给迁移在开业前按发布窗口执行。

### 5.3 迁移序列（父点 20260921_staff_scope，串行）

1. `20260923_project_templates`：建 4.1/4.2/4.3 三表 + projects.template_id 回填（14 项目 → 14 模板，价格快照复制为初始标准价与本店有效价，逐项一致性校验对齐 spec §9.2）
2. `2026092x_store2_provisioning`：门店 2 供给（文件名按实际执行日定）
3. 历史账号兼容已由 BRAND-ACCESS-003 处理，本序列不含账号变更

- 全部新迁移走两步许可模式：业务 PR 不含白名单条目，许可 PR 单独加入。
- 发布顺序沿用"备份校验 → 隔离恢复 → 隔离升级 → 生产升级"；生产不执行 downgrade。

## 6. 实施拆分

| PR | 范围 | 依赖 |
|---|---|---|
| PR1：目录模板 schema | 4.1–4.3 三表 + 迁移 1 + 回填校验测试 | 集成分支合入主干后 rebase |
| PR2：价格解析与写入契约 | 有效价解析 helper、覆盖价写入校验、品牌停用拦截、审计上下文 | PR1 |
| PR3：单店假设盘点清除 | G3 代码盘点：公开目录门店参数化、QR/内容入店绑定复核、admin 作用域默认 | 与 PR1 并行 |
| PR4：门店 2 供给 | 迁移 2 + 供给校验脚本 + 开业前演练 | PR1 + 门店 2 物理参数确认 |
| PR5：管理后台界面 | 总部模板页、门店价格/上下架页（对齐既有 spec §6） | PR2 |

## 7. 验证和完成标准

### 7.1 自动验证

- 迁移图单头线性断言随新末端头更新（test_task2_alembic_chain、test_alembic_contract）
- 回填一致性：迁移前后项目数量、ID、状态、有效价格逐项相等
- 价格解析：强制价/覆盖合法/覆盖越界拒绝/品牌停用拒绝四类用例
- 跨店隔离：门店 2 种子数据存在时，门店 1 公开目录、订单、选单零变化
- 授权：店长仅能写授权门店覆盖价，越界返回稳定错误码（BRAND-ACCESS-003 语义）

### 7.2 生产与现场验收

- 备份校验、恢复演练、隔离升级、生产升级分步记录
- 门店 2 开业前：供给迁移演练库全量跑通，公开目录双店探针比对
- PG 真实并发验证（交接阻塞项 3）须在本序列首个发布前关闭

## 8. 未决问题（需业务确认）

1. **G5 会员权益跨店规则**：品牌通用还是门店限定？影响 membership 域是否需新增品牌级作用域列。
2. **门店 2 物理参数**：store_code、店名、房间/沙发/床位数量与编码起始值（供给迁移的显式常量来源）。
3. **顾客端门店选择**：diy.hexiaoyue.com 当前 store_id=1 硬绑定；门店 2 的顾客入口是独立站点/二维码分流还是店选页？影响 G3 的改造范围。
4. **会员价开关**（member_price_enabled，catalog 退役 backlog）是否随 PR1 一并立项。

## 9. 已考虑方案

- **采用**：在既有授权底座（BRAND-ACCESS-003）与冻结 spec（BRAND-CATALOG-004）上补齐三层目录 schema——复用已交付约束与审计，迁移面最小。
- **不采用**：全量表加 store_id 的大水漫灌——顾客身份等全局表加作用域反而破坏跨店识别；现状盘点显示数据隔离主体已完成。
- **不采用**：rooms.code 复合唯一化——见 5.1。

## 10. 收敛检查

- [x] 迁移父点明确（20260921_staff_scope），图保持单头线性
- [x] 门店 1 公开价格与历史引用不被迁移改变
- [x] 与 BRAND-ACCESS-003/BRAND-CATALOG-004 的边界无重叠无冲突
- [x] 物理资源操作仍归智慧宝，不进入本仓库
- [x] 业务未决项已显式列出，不代为决策
