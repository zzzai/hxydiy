# Astra 指令审计（2026-09-08）

## 依据与读取情况

- OpenAI Model Guidance：https://developers.openai.com/api/docs/guides/latest-model 。已读取官方 Markdown 全文。
- Eric Provencher（实际账号 @pvncher）：https://x.com/pvncher/article/2095991462416490862 。X 未能访问；已读取搜索引擎索引的英文转载正文，含 Skill files、AGENTS.md、Decision boundaries、Persistence 全部章节：https://en.rattibha.com/thread/2095991462416490862 。未核验文章中的图片内容。

## 生效范围

当前项目自动入口为根目录 AGENTS.md；仓库检索未发现嵌套 AGENTS.override.md 或 SKILL.md。用户级 AGENTS.md 仅规定中文回复与英文代码/命令；已检查的父目录未发现额外 AGENTS 文件。config.toml 定向检索未发现自定义 instruction 文件指向，不修改模型、插件或权限设置。

docs/CONTEXT-MANIFEST.md 和 docs/script-first-delivery.md 经 AGENTS 引用影响工作流，已同步调整。docs 中的 PRD、计划与历史交接仅作为任务资料，不能自动扩充当前授权。

## 发现与处理

| 来源 | 问题 | 本项目处理 |
|---|---|---|
| 用户级 using-superpowers/SKILL.md | 1% 可能性就加载技能、任何回复前强制技能 | 仅按实际需要选技能 |
| 用户级 brainstorming/SKILL.md | 所有改动均设计审批，书面 spec 再审批 | 已有批准直接执行，重大未决选择才询问 |
| 用户级 writing-plans/SKILL.md | 逐步代码计划、固定提交粒度、再次询问执行方式 | 计划规模与任务相称，常规实现选择自主决定 |
| 用户级 executing-plans/SKILL.md | 有 subagent 即转委派，按步骤照做，缺依赖或测试失败就停 | 单代理默认，处理任务内常见失败，具体阻碍才暂停 |
| 用户级 test-driven-development/SKILL.md | 所有变更强制 RED/GREEN，测试镜像实现 | 保留关键行为回归，低风险文案/指令不新增仪式性测试 |
| 项目 AGENTS 与 CONTEXT-MANIFEST | 每次任务必读三份资料，任何任务先 worktree | 新接手及跨端/发布读取；连续工作复用上下文；只读任务免 worktree |
| 项目 AGENTS 与 script-first-delivery | 启动等待必须结束回合 | 后台等待期间继续独立工作，交接时明确未完成状态 |
| CONTEXT-MANIFEST | 生产事实排序容易误解为授权或业务优先级 | 明确事实核验不覆盖业务契约和用户授权 |
| AGENTS 的历史建设目录 | 里程碑结束后要求删除目录 | 保留非运行时边界，移除自动清理暗示 |

用户级技能原文件未修改，它们服务所有项目；本次使用项目明确指令约束其通用流程。平台注入的 system/developer 指令不能通过仓库文件修改。本次不卸载其他技能，不修改记忆库，不变更业务代码或 GitHub CI。

## 保留

未提交代码保护、独立开发工作区、跨端契约同 PR 更新、主干共享记忆、凭证与隐私保护、精确 SHA 与分支保护、迁移审批、备份恢复演练、Manifest、健康检查、现有回滚边界，以及本地/合并/生产/现场验收的证据区分。

## 验证和生效

检查修改差异及 Markdown 空白，运行现有共享上下文合同（如存在）。不因纯指令调整触发应用构建或生产部署。修改在本审计分支生效；其他窗口需通过主干同步，旧会话已注入的指令不会被磁盘修改自动撤回。
