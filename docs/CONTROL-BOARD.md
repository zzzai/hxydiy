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

| Feature ID | 事项 | 状态 | 总控负责人 | 执行窗口 | 权威规格/契约 | 下一门禁 |
|---|---|---|---|---|---|---|
| `PLATFORM-CONTRACT-001` | 项目与商品管理 OpenAPI、生成类型及 Schemathesis 试点 | `Merged` | 总控窗口 | 总控；契约冻结后按需启用管理端窗口 | `docs/superpowers/plans/2026-09-21-contract-governance-and-api-validation.md` | PR #118、#119、#120 已合并；工具链无需生产部署，后续随业务变更持续验证 |
| `ADMIN-CATALOG-002` | 商品目录首期可运营闭环 | `Integrated` | 总控窗口 | 管理后台 | `docs/specs/ADMIN-CATALOG-002.md` | 本地集成验证通过；下一门禁为提交、PR 与可信 CI |

## 总控规则

- 总控窗口维护优先级、Feature ID、跨端依赖、契约冻结、集成验证和交付证据；端窗口不复制本看板。
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
