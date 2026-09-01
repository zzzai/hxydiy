# 营销 Skill 套件实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `C:\Users\gaoji\.codex\skills\` 创建 8 个营销专项 Skill 和 1 个总控 Skill，支持独立调用与端到端活动编排。

**Architecture:** 每个 Skill 是独立目录中的 `SKILL.md`，只包含触发条件、关键决策和结构化交付契约。总控 Skill 通过读取用户输入和上游结果串联专项能力，不调用外部系统，不执行发布或投放。

**Tech Stack:** Markdown、YAML frontmatter、Skill Creator `init_skill.py` 与 `quick_validate.py`。

## Global Constraints

- 默认允许自动发现；专项 Skill 必须可单独调用。
- 不编造消费者研究、市场数据、产品能力或效果承诺。
- 区分证据、推断、假设和建议；信息不足时明确列出待确认事项。
- 不执行广告账户操作、公开发布、敏感受众数据传输或替用户作合规审批。
- 涉及受监管行业时提示领域审核。
- 使用简体中文输出；文案 Skill 可按用户指定语言产出。
- 不新增脚本、资产或第三方连接器。

### Task 1: 初始化 9 个 Skill 目录

**Files:**
- Create: `C:\Users\gaoji\.codex\skills\customer-research\SKILL.md`
- Create: `C:\Users\gaoji\.codex\skills\marketing-psychology\SKILL.md`
- Create: `C:\Users\gaoji\.codex\skills\brand-positioning\SKILL.md`
- Create: `C:\Users\gaoji\.codex\skills\content-strategy\SKILL.md`
- Create: `C:\Users\gaoji\.codex\skills\ad-creative\SKILL.md`
- Create: `C:\Users\gaoji\.codex\skills\copywriting\SKILL.md`
- Create: `C:\Users\gaoji\.codex\skills\social-content\SKILL.md`
- Create: `C:\Users\gaoji\.codex\skills\campaign-analytics\SKILL.md`
- Create: `C:\Users\gaoji\.codex\skills\marketing-orchestrator\SKILL.md`

- [ ] **Step 1: 初始化目录**

运行以下命令，为每个 Skill 创建规范目录和入口文件：

```powershell
$skillRoot = 'C:\Users\gaoji\.codex\skills'
$init = Join-Path $skillRoot '.system\skill-creator\scripts\init_skill.py'
'customer-research','marketing-psychology','brand-positioning','content-strategy','ad-creative','copywriting','social-content','campaign-analytics','marketing-orchestrator' | ForEach-Object {
  python $init $_ --path $skillRoot
}
```

预期：9 个目录各包含 `SKILL.md` 和 `agents/openai.yaml`，不生成 `scripts`、`references` 或 `assets`。

### Task 2: 编写专项 Skill 指令

**Files:**
- Modify: 8 个专项 Skill 的 `SKILL.md`

**Interfaces:**
- 每个入口接收自然语言任务和可选上游结果。
- 每个入口输出“结论/建议、依据或假设、待确认事项、下一步交接字段”。

- [ ] **Step 1: 为每个 Skill 写入 frontmatter**

使用短、可区分的 `name` 和 `description`，描述实际能力与触发边界，不使用 catch-all 描述。

- [ ] **Step 2: 写入专项工作流**

每个 Skill 至少包含：输入检查、核心分析步骤、固定交付结构、事实与假设分离、安全边界。按职责写入以下专属要求：

```text
customer-research：来源分层、证据摘录、痛点/动机/场景、冲突证据和待验证假设。
marketing-psychology：动机、阻力、社会证明、风险感知和信息框架；禁止操纵和歧视性定向。
brand-positioning：目标受众、替代方案、差异化、定位陈述、信息支柱、语气和禁用表达。
content-strategy：内容支柱、渠道选择、用户旅程、选题池、节奏、资源限制和日历字段。
ad-creative：创意切角、钩子、视觉/视频要求、CTA、变体和 A/B 测试矩阵。
copywriting：按渠道产出标题、正文、CTA、长度和合规说明；不得虚构数据或承诺。
social-content：把核心主张适配小红书、抖音、微信、LinkedIn 等渠道，保留平台语境和格式要求。
campaign-analytics：指标树、事件定义、归因假设、实验设计、复盘和下一轮行动；不把相关性写成因果。
```

- [ ] **Step 3: 检查边界**

确认专项 Skill 不会默认调用其他 Skill，不会执行外部发布，不会索取不必要的个人敏感信息。

### Task 3: 编写总控 Skill

**Files:**
- Modify: `C:\Users\gaoji\.codex\skills\marketing-orchestrator\SKILL.md`

**Interfaces:**
- 输入：营销目标、产品/服务、受众、渠道、地区/语言、时间、预算/资源、已有证据和合规限制。
- 输出：活动简报、证据与假设、定位、内容策略、创意矩阵、渠道文案、指标计划、风险和待批准事项。

- [ ] **Step 1: 定义路由**

默认按 `customer-research → marketing-psychology → brand-positioning → content-strategy → ad-creative → copywriting → social-content → campaign-analytics` 编排；已有结论时跳过对应环节并说明原因。

- [ ] **Step 2: 定义质量门禁**

总控在交付前检查主张有依据、渠道规格齐全、CTA 清晰、指标可观测、假设已标记、受监管内容有人工审核提示。

- [ ] **Step 3: 定义停止条件**

缺少关键输入时先输出最小澄清问题；无法验证的效果不写成承诺；涉及外部发布或敏感数据时停在待用户批准状态。

### Task 4: 生成 UI 元数据并验证

**Files:**
- Modify: 9 个 Skill 的 `agents/openai.yaml`

- [ ] **Step 1: 设置显示名称和默认提示**

为每项 Skill 设置清晰的 `display_name`、`short_description` 和 `default_prompt`，保持自动发现开启。

- [ ] **Step 2: 运行规范验证**

```powershell
$validate = 'C:\Users\gaoji\.codex\skills\.system\skill-creator\scripts\quick_validate.py'
'customer-research','marketing-psychology','brand-positioning','content-strategy','ad-creative','copywriting','social-content','campaign-analytics','marketing-orchestrator' | ForEach-Object {
  python $validate (Join-Path 'C:\Users\gaoji\.codex\skills' $_)
}
```

预期：9 项均通过；不得出现未替换的脚手架占位符。

### Task 5: 路由验收与记录

**Files:**
- Modify: `C:\Users\gaoji\Documents\ChatGPT\hxy-diy\docs\WORK-STATUS.md`

- [ ] **Step 1: 运行两条路由样例**

检查“为新品做完整小红书和抖音推广方案”进入总控，“把卖点改成 3 条朋友圈文案”进入文案/社媒专项，不强制完整链路。

- [ ] **Step 2: 更新工作状态**

记录创建的 Skill、验证结果、使用边界和未完成事项；不记录任何真实账号、手机号、密钥或顾客信息。

- [ ] **Step 3: 提交**

```powershell
git add C:\Users\gaoji\.codex\skills\customer-research C:\Users\gaoji\.codex\skills\marketing-psychology C:\Users\gaoji\.codex\skills\brand-positioning C:\Users\gaoji\.codex\skills\content-strategy C:\Users\gaoji\.codex\skills\ad-creative C:\Users\gaoji\.codex\skills\copywriting C:\Users\gaoji\.codex\skills\social-content C:\Users\gaoji\.codex\skills\campaign-analytics C:\Users\gaoji\.codex\skills\marketing-orchestrator docs/WORK-STATUS.md
git commit -m "feat: add modular marketing skill suite"
```
