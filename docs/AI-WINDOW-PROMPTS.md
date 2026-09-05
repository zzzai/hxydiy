# 三端开发窗口启动提示词

本文件只提供短启动指令。项目事实从 Git 主干和共享记忆读取，不把完整背景复制进提示词。

## 公共启动提示词

```text
你正在维护 hxy-diy Monorepo。先读取根目录 AGENTS.md。保存当前未提交工作后执行 git fetch origin，并确认当前任务分支已经合入或 rebase 到最新 origin/main；不要覆盖其他窗口的工作。然后只读取 docs/CONTEXT-MANIFEST.md、docs/CURRENT-STATE.md 和本端 workstream。涉及 API、价格、状态机、权限、服务位或画像字段时，再读取 docs/TEAM-MEMORY.md、相关 docs/contracts/、源码和合同测试。聊天、未提交文件和旧提示词不是共享事实源。
```

## 三端公共交付规则

```text
完成本地验证和本次授权提交后，按 docs/script-first-delivery.md 启动 tools/release/start-release-watch.ps1。正常等待交给脚本，报告路径交给用户后结束本轮，不让模型循环轮询。下次先读取 report.json；terminal=false 不宣称完成，失败/超时/冲突才读必要的失败片段。未经授权不传 -Merge，不自动重跑或手工重复部署。脚本不调用模型，云端 AI 审查默认关闭；不要把整项研发宣称为零 token。
```

## 顾客端窗口

```text
你负责 diy-web/ 和 docs/workstreams/customer.md。负责扫码、服务位绑定、菜单、价格、会员/匿名选单、提交、服务状态、评价和顾客端移动体验。不要实现技师操作、管理后台权限或智慧宝物理资源操作。完成后运行顾客端测试和生产构建；跨端契约变化与实现、合同测试和共享记忆进入同一个 PR。
```

## 管理端窗口

```text
你负责 admin-react/ 的管理后台页面、相关管理 API 契约和 docs/workstreams/admin.md。负责总部管理员、店长、普通员工工作台、目录、门店、服务位、技师档案、运营只读数据和权限呈现。技师移动端页面由技师端窗口负责。不要实现顾客选购、DIY 派单或智慧宝物理资源写操作。完成后运行管理端测试、TypeScript 检查、生产构建和受影响后端合同测试。
```

## 技师端窗口

```text
你负责 admin-react/src/technician/、技师相关后端、合同测试和 docs/workstreams/technician.md。负责技师账号、移动看板、确认服务、服务结束、服务参考、本人历史和审计。不要实现派单、接单、排班、结算、跨店查询或智慧宝物理资源写操作。完成后运行技师后端专项、管理端测试和生产构建；画像契约变化必须同步 TEAM-MEMORY 和相关 contract。
```

## 其他窗口合并新记忆后的操作

```text
先提交或暂存当前窗口改动；执行 git fetch origin；把最新 origin/main 合入或 rebase 到当前任务分支；发生冲突时保留本端业务改动，并以 origin/main 的 CURRENT-STATE、TEAM-MEMORY 和 contracts 为共享事实。重新开始任务后按最小上下文规则读取文件，不复制旧聊天。
```
