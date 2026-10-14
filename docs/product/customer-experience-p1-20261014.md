# CUSTOMER-EXPERIENCE-P1-20261014 Implementation Plan

**Goal:** 修复顾客选购数量/关联加购与受控追加的高风险逻辑，统一本人报告入口，并交付本地可点击预览。

**Architecture:** 复用既有选单、修订、报告API及当前白底深绿UI。保持前台审批、价格冻结、共享草稿权限及本人报告归属，先复现后修正，不做全站重构。

**Baseline:** 本批各端及统一候选的BASE/HEAD为 `bb3e57e0ad48d562e3927862c87ce8904a70e118`；相对业务基线 `6b139f8f9a5dadbe99beb67af705a75d6c8f7d12` 仅增加历史发布记录文档，不据此推定当前生产安装。隔离分支 `codex/customer-experience-fixes-20261014`。业务审计证据为 `C:/Users/gaoji/.codex/worktrees/customer-detail-preview/hxy-diy/output/customer-ux-audit-20261014/AUDIT.md`，仅供分析，不被运行时代码读取。

**Execution:** 三个现有端窗口负责各自业务/验收，总控只协调、共享契约及机械组装候选。有效同源码验证复用；最终构建由总控安排顾客端唯一执行，不在多个工作区重复构建。实施和审查事实见同工作区ignored `output/project-control/current-progress.md`，该账本不代表已合并共享事实。

**Local acceptance:** 本批源码限定本地集成验收已完成；顾客端从完整统一候选恢复4199安全合成预览，总控已独立确认实际报告跳转及Back返回报告中心，19源码SHA未变。证据、合成顾客/UI覆盖及未验范围见 `../operations/customer-experience-p1-local-acceptance-20261014.md`。勾选不表示提交、合并、生产或现场通过；原临时路径不可用的原因仍未确认，历史/异常空身份展示加固为独立后续建议，未实施。

**Delivery continuation:** 用户于2026-10-14明确授权本批提交、PR、必需CI通过后合并及服务器验证后发布生产。由总控唯一执行；下列“本轮本地/没有发布”描述原实施与验收阶段，不撤销此新增交付授权。实际合并及生产结果需另以精确SHA、发布报告和实时核验记录，不能由本计划推定。禁止夹带新功能、权限扩张、数据清理或未授权DB/凭据变更。

## Global Constraints

- 不改项目价格、时长、活动、素材、IP、支付模式、门店数据；本轮无数据库迁移、凭据及权限扩张。
- 多浏览器仅共享未提交草稿；一经提交锁定同行者，发起人有本人凭证才可走既有受控追加；不得通过放开协作权限修复。
- 不读取真人报告、照片、生产短信或真实选单；测试使用隔离数据。生产服务位与审批均不用于测试。
- 本轮交付本地实现、回归证据、可点击预览及审查；没有生产发布。API/状态/导航语义同步写契约与TEAM-MEMORY，并与业务纳入同一候选变更。
- 当前UI保留；报告返回中心采用已批准的“最近报告、历史、浏览门店项目、更多”结构，不新生图、不新增独立授权页。已有v2本人动作、归属、失效、撤回及原站no-referrer校验保持。
- 代码/命令/注释英文；用户文案中文。使用apply_patch编辑，不覆盖其他任务文件，不自行提交、推送、合并或发布。

## Task 1: Customer purchase state and entry integration

**Owner:** 现有「顾客端」窗口，合并承接Task 1与Task 3，唯一写顾客端业务文件。总控原执行代理已中断，不再实施。

**Files:** `App.tsx`、`selectionSummary.ts`、`domain.ts`、必要的选购纯函数/helper、`components/ProjectDetailPage.tsx`、对应测试；报告入口helper `returnEntry.ts` 及入口测试也由本任务唯一写。

**Result/acceptance:**

- [x] 先复现A两份→保存A或B详情，数量必须仍为两份；报价/载荷同步一致。
- [x] published关联B的勾选→保存→取消→保存必须撤销该来源；独立选购B或其他主项关联B不被删除；数量与来源必须可区分，不能简单全局去重或全局删除。
- [x] 首次扫码发起人提交后报价/修订转本人凭证路径；同行者提交后仍只读；共享草稿并发version/冲突/幂等不减弱。
- [x] 对 submitted/confirmed 的再次选购，原服务快照与本次新增草稿区别明确；与后端任务约定全量/增量输入，避免重复累计。
- [x] 首页、座位页、个人中心报告按钮进入统一专用报告入口；现用显式 `view=return` 企微链接兼容该报告任务，裸门店回访及QR/分享优先级不顺带改；URL仅含门店/专用view，不携带凭据。
- [x] 在 `ProfilePage` 接收报告任务的回调处接入Task 3约定；本任务不写报告组件。
- [x] 先失败的行为测试→最小修复→相关回归；最终构建由总控安排同候选唯一执行一次。

**Interfaces:** 现有选单API与来源可追踪的本地草稿，后端修订由Task 2明确；个人页新增 `onOpenReports?: () => void` 由Task 3提供并在App各实例传入。

## Task 2: Revision quantity delta and contract verification

**Owner:** 现有「管理后台+后端」窗口。只写 `hxy-server/` 必需的服务/领域逻辑及测试，不写顾客代码或共享文档。

**Result/acceptance:**

- [x] 用真实HTTP/领域路径复现同配置1→2、2→3及confirmed服务中再次选同配置的数量遗漏；记录实际请求是全量还是增量，不依赖猜测。
- [x] 在既有受控修订语义内计算新增数量差；相同配置原单位不重复附加，不同配置仍新增；不能把全量行直接当新增行。
- [x] 提交申请不改原单，审批才落入服务及价格；失败、拒绝、重复请求与重复审批不重复追加。
- [x] 保留门店隔离、人员权限、原价冻结、版本/冲突及同行者只读的合同验证。
- [x] 测试先失败后修复；只在本地隔离测试数据执行，严禁生产凭据/数据。与Task 1先共享全量/增量约定再实现。

**Interfaces:** 既有 `POST /selections/{id}/revisions` 与前台修订审批；尽量不改外部schema。必要语义变更先通知控制窗口和顾客代理。

## Task 3: Report center and account report action

**Owner:** 现有「顾客端」窗口，与Task 1同一写入负责人；报告组件、个人中心报告回调及入口文件不再由总控下两个执行代理分别改动。共享文档由总控整合。

**Result/acceptance:**

- [x] 已批准结构：首次明确“登录并查看报告”成功直接打开最新有效原站报告；看完Back返回可再次查看最近报告、展开历史、浏览门店项目的中心，不自动再打开。
- [x] 菜单入口同源无座位公开目录，不创建占用/选单；更多承载换号码及既有报告设置/撤回，不能移除撤回渠道。
- [x] 首次明确动作/有效v2复用、失效/403/换号/迟到请求/暂无报告/最新链接不可用仍真实反馈；不猜最新或原站地址，不新增勾选页/独立授权页。
- [x] ProfilePage新增可选 `onOpenReports` 回调，报告按钮优先回调；不改普通登录、价格或用户历史功能。
- [x] 直接打开入口的返回有确定退路；保留实际浏览器历史，不强制跳菜单，不额外塞入首页记录。
- [x] 原站仍 `_self` + no-referrer，严守手机号、报告ID归属；不iframe、分享、照片代理或测试真报告。
- [x] 只改变报告中心信息层级，复用现有UI，不移植模拟手机号或生产测试例外。
- [x] 合理粒度行为测试，用户文案/排版不做源码字符串测试；浏览器交互验收由控制窗口统一做。

**Reference:** 已批准本地候选 `C:/Users/gaoji/.codex/worktrees/customer-detail-preview/hxy-diy/output/report-return-preview-20261014/`，仅视觉/交互参考，不是运行时依赖。

## Controller integration and handoff

- [x] 三任务各提供文件归属、红/绿测试命令与输出及当前限制，执行代理不提交。
- [x] 控制窗口单一维护 `docs/contracts/customer-shared-selection-v1.md`、`customer-return-entry-v1.md`、`tcm-my-reports-v1.md`、`TEAM-MEMORY.md` 和customer workstream；只写本地候选，不假称已合并/上线。
- [x] 审查任务diff与交叉接口，针对真实风险修复；有效同SHA测试不重复跑。
- [x] 整合后顾客构建、相关前后端回归与一次手机浏览器验收；本地API使用合成数据，不向生产转发写操作。
- [x] 恢复并重新交付真实App可点击预览和差异说明；4199当前可用，接口和原站报告均为本地合成数据，恢复时未改19源码或重复构建/测试。范围外P2（详情运营内容、UI重排、弱网等）记录后续，不夹带大改。

## Deferred from audit

公开浏览DIY临时意图承接、详情模板文案、主图槽位、储值会员称谓、弱网同步、模态焦点及运营密度不在本批全面重做。若本批修复依赖其中某个最小点，须明确记录依据与增量边界。
