# hxy-diy 总控看板

本文件是跨端工作的控制平面，只记录当前仍需推进的业务能力、依赖和可验证状态。它不复制 PRD、API 契约、端内工作流或发布历史；这些事实继续使用各自的权威文件。

## 状态模型

`Candidate → Spec Ready → Contract Frozen → Developing → Integrated → Merged → Deployed → Field Accepted`

- `Candidate`：候选事项，尚未形成可执行增量规格。
- `Spec Ready`：目标、非目标、业务规则和验收标准已明确。
- `Contract Frozen`：跨端 API、权限、状态和数据范围已冻结。
- `Developing`：一个或多个执行窗口正在独立 worktree 实现。
- `Integrated`：相关实现已在同一分支完成本地集成验证。
- `Merged`：精确提交已合并到 `origin/main`。
- `Deployed`：精确主干提交已完成生产发布和服务器核验。
- `Field Accepted`：真实设备或门店营业场景已经验收。

状态只能依据对应证据前进，不能把计划、本地测试、CI、部署任务或公网探针互相替代。

## 当前事项

### 2026-10-01 评审整改批次

用户已授权总控负责执行整体评审规划。规格与复现证据见 `docs/reviews/project-review-20261001.md`；实时交付记录见 `docs/operations/execution-20261001.md`。下列条目优先于历史批次的下一门禁描述；没有最终回执不得标为完成。

| Task ID | 状态 | 唯一执行窗口 | 范围与下一门禁 |
|---|---|---|---|
| `SAFE-01` | `Deployed` | 管理后台＋后端 | PR #182 已随 `08d73c89d057` 发布；服务器与主干文件hash一致，现场验收后续安排 |
| `PRICE-01` | `Deployed` | 管理后台＋后端 | PR #183 已随 `08d73c89d057` 发布；来源年度/储值确认矩阵通过、历史冻结，现场后续安排 |
| `OPS-01` | `Deployed` | 总控 | #185 的3GiB容量门禁已随 `28e140fbff72` 发布；容量约90%，具体清理/异机备份与告警仍待核验 |
| `MEMBER-02` | `Deployed` | 管理后台＋后端 | #184/#186 已随 `28e140fbff72` 发布，真实PostgreSQL并发CI通过；没有真实卡事实更新，运营频率待确定 |
| `CUSTOMER-02` | `Deployed` | 顾客端 | #187 共享选单弱网/在途去重/可见性恢复已随 `28e140fbff72` 发布；模拟证据见FIELD-SIM-01 |
| `TECH-02` | `Deployed` | 技师端 | #188 重试与生命周期提示已随 `28e140fbff72` 发布；本地验证及模拟API流程通过，真实技师UI现场待验收 |
| `CUSTOMER-03` | `Deployed` | 顾客端 | #189 偏好清单、SPA推荐标价、详情首屏与结算提示已发布；赠泡/额外另购语义随新菜单继续收敛，不宣称全部五项业务已闭环 |
| `FIELD-SIM-01` | `Merged` | 顾客端 | #190 模拟脚本/记录已合并并随本批发布；375/390、8张合成码、共享弱网及API服务释放通过；不等于真实微信/门店验收 |
| `MENU-20261001` | `Developing` | 管理后台＋后端 | 最新14项菜单已交单一窗口，从最新主干隔离实现；范围及未决条件见 `operations/menu-handoff-20261001.md`，尚未生产应用 |
| `FIELD-01` | `Spec Ready` | 总控组织门店 | 用户明确先完成开发、现场稍后安排；逐位/双设备/真实会员/完整服务矩阵已在评审中定义 |

用户2026-10-01最新要求“先不考虑额度，直至用完”，本次取消12%停止及10%预留限制；实际耗尽保存交接，不自动切换模型或重置额度。仍遵循单窗口、小批、脚本等待，不重复已有效验证。最近正式发布为 `28e140fbff726992c39a9a1aaa8f3794e75abde8` / `36820787691`，current、MANIFEST与health已核，生产发布串行，合并不等于发布。

### 既有能力

| Feature ID | 事项 | 状态 | 总控负责人 | 执行窗口 | 权威规格/契约 | 下一门禁 |
|---|---|---|---|---|---|---|
| `PLATFORM-CONTRACT-001` | 项目与商品管理 OpenAPI、生成类型及 Schemathesis 试点 | `Merged` | 总控窗口 | 总控；契约冻结后按需启用管理端窗口 | `docs/superpowers/plans/2026-09-21-contract-governance-and-api-validation.md` | PR #118、#119、#120 已合并；工具链无需生产部署，后续随业务变更持续验证 |
| `ADMIN-CATALOG-002` | 商品目录首期可运营闭环 | `Deployed` | 总控窗口 | 管理后台 | `docs/specs/ADMIN-CATALOG-002.md` | 生产 release `github-c76ac301efa0-35576431361`、迁移与公网核验已通过；下一门禁为总部/店长授权账号与门店营业现场验收 |
| `CUSTOMER-MENU-SYNC` | 营业中顾客菜单同步 | `Deployed` | 总控窗口 | 顾客端 | PR #132 `feat: refresh customer menu during active visits` | 已随 `34fab31` 发布；下一门禁为营业中更新菜单的真机与门店验收 |
| `CUSTOMER-SCAN-FEEDBACK` | 同一扫码入口待评价提醒与独立到店反馈 | `Deployed` | 总控窗口 | 顾客端、管理后台 | `docs/contracts/open-visit-feedback-v1.md`；PR #133 | 已随 `34fab31` 发布；下一门禁为逐床打印张贴签名码，以及匿名/登录、无选单评价和门店隔离现场验收 |
| `TECHNICIAN-HANDOFF` | 技师服务后快速交接 v7 | `Deployed` | 总控窗口 | 技师端 | `docs/contracts/service-handoff-v1.md`；`docs/workstreams/technician.md` | 主干与生产发布事实已记录；下一门禁为真实微信、弱网、重复提交和门店营业现场验收 |
| `BRAND-ACCESS-003` | 连锁品牌账号、角色与作用域授权（PR 1） | `Deployed` | 总控窗口 | 管理后台 | `docs/superpowers/specs/2026-09-21-chain-brand-access-and-catalog-design.md`；`docs/contracts/admin-catalog-openapi-v1.md` | PR #130 已合并并随 `34fab31` 发布；`admin` 的总部及 1 号店店长工作区已落库，下一门禁为现场权限验收 |
| `BRAND-CATALOG-004` | 总部项目模板与门店价格覆盖（PR 2）及管理界面（PR 3） | `Spec Ready` | 总控窗口 | 管理后台 | `docs/superpowers/specs/2026-09-21-chain-brand-access-and-catalog-design.md`；`docs/superpowers/plans/2026-09-21-brand-catalog-pricing.md`；`docs/superpowers/plans/2026-09-21-admin-workspace-ui.md` | PR 1 已发布；PR 2 应从最新主干独立推进，PR 3 待 PR 2 契约稳定后实施，不与本次门店二维码验收混在一批 |

## 总控规则

### 2026-09-23 恢复批次

- `CUSTOMER-FEEDBACK-005`：PR #133 已合并并随 `34fab31` 发布；签名服务位码、独立到店反馈和后台处理入口进入生产。门店未贴码，现场验收仍未完成；历史集成证据见 `docs/operations/feedback-recovery-20260923.md`。
- 本批次不叠加 `wb-multi-store` 的模板/价格扩展；保留该分支成果，待评价链路与迁移应用历史核验后继续。
- 下一门禁：1 号店店长工作区重登，逐床打印并张贴正式签名码，真机验证直接评价和处理闭环。数据库迁移与生产发布已完成，不重复派发。

- 总控窗口维护优先级、Feature ID、跨端依赖、契约冻结、集成验证和交付证据；端窗口不复制本看板。
- 状态校准门禁：总控在回答跨窗口状态或下发正式任务前，必须实时核对相关窗口的 `branch/HEAD`、`git status`、相对 `origin/main` 的前后提交数、PR/合并/生产证据和共享文件重叠；不得从窗口标题、旧聊天摘要或“窗口开着”推断正在开发。
- 任务开始、跨端契约变化、PR 创建、合并、发布五个节点必须重新校准；共享后端、API 与 OpenAPI 同时只指定一个写入窗口。
- 端窗口统一分开回报本地、提交、推送、PR、合并、生产、现场验收七种状态，缺少证据的状态不得向后推断。
- 日常任务默认只启动“总控窗口 + 一个相关执行窗口”；确有独立跨端工作时才增加并行窗口。
- 公共后端模型、价格、会员、权限、状态机、OpenAPI 和 CI 由总控窗口协调；端专属接口可由对应端窗口实现。
- 跨端契约变化必须在同一个 PR 更新业务实现、合同测试、`docs/TEAM-MEMORY.md` 和相关 `docs/contracts/`。
- 合并或发布后，总控删除已失效的临时依赖描述；历史事实进入 Git、`docs/WORK-STATUS.md` 或相关 workstream，不在本文件堆积。

## 完成证据

每个事项至少记录以下证据，缺失项保持在相应状态：

- 增量规格与明确非目标；
- 冻结的契约或“不改变契约”的证据；
- 受影响端的专项测试和构建；
- Pull Request、完整 head SHA 和合并 SHA；
- 生产发布报告与服务器 `current` 核验；
- 需要现场验证时的设备、角色、场景和结果。
