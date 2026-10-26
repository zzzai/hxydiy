# DeepSeek 接管与评价闭环 · 2026-10-26

## 2026-10-27 评价闭环修复已上线，新增扫码企微提醒尚未启用

- [PR #399](https://github.com/zzzai/hxydiy/pull/399) 已合并；候选 `cf884537f4ce972df51ec5c063e9807692f09900`，合并/运行版本 `abbdbd9aa20c767dc13259c7504fa75a28481c62`。精确 [CI 40357711435](https://github.com/zzzai/hxydiy/actions/runs/40357711435) 与唯一 [Deploy 40358856792](https://github.com/zzzai/hxydiy/actions/runs/40358856792) 成功，备份、恢复演练、部署和验证 job 通过；实际 current=`github-abbdbd9aa20c-40358856792`。
- 服务评价与独立扫码评价共同进入店长评价列表和低分待办；类型与 ID 共同定位，OAuth 回跳保留正确来源。跟进连续点击只保存一次，失败保留输入，可重试并回读。审计以中文结果和数量展示。
- 新增扫码评价通知开关在生产实际为 false，未发送本批真实测试卡，未补发历史评价。启用和一条店长验收卡等待用户明确外发授权；原服务评价触发范围保留。API accepted 仅表示受理，不代表送达/已读；进程内 best-effort 不等于可靠队列。
- 只读验收通过 520 项 MANIFEST、170 个安装 Python 文件、7 个运行文件及 10 个公网入口/资源哈希；health=`ok/production`，备份 checksum 通过。迁移集合与前一版完全一致；未新增数据库迁移或清理旧数据。核验业务 API 调用、数据库查询和业务写入均为 0。
- 隔离后端 74 项、前端定向 19 项、真实 React 合成浏览器 6 组及类型/构建/必需 CI 通过；真实企微/门店验收交由人员。店长每日必做及两入口简化界面仍仅在原独立预览工作区，未混入本批。
- 证据：`output/takeover-20261026/production-verification-abbdbd9aa20c-40358856792.json`、`deployment-result.json`、`production-notification-flag.json`；操作边界见 `operations/takeover-feedback-20261026.md`。此次事实文档补录不再次部署应用。

## 基线和归属
DeepSeek 目标 UI 已暂停。末次 PR #398 已合并、CI/Deploy 成功，总控只读确认生产 a6ab7bf0d8d06949db407777edc82016a1002407；没有重复发布。实现工作区 `/root/hxy-diy-development/takeover-feedback-notify-20261026`，分支 `codex/takeover-feedback-notify-20261026`。从 GitHub 当前主干哈希核验导入，不覆盖旧分支或脏文件。

`manager-daily-checklist-20261025` 是原店长每日必做/两入口预览，保持原状。会员自动同步继续原独立受控流程，不在本批改动。不得将本地旧分支、HXYOS 或历史 production 文档当作实时运行事实。

## 实施阶段范围（历史）
两类评价共同显示、OAuth 直达、独立扫码通知触发（默认关闭）、结果审计投影、跟进同步防重复。未新增表、未发真实消息、未读写生产业务数据、未提交/合并/发布此批。当前证据绑定未提交文件 SHA 清单，最终 CI 需绑定正式提交 SHA。

## 已做验证
- 后端定向首次 73 passed / 1 failed；失败是合成测试状态填错，修为现有 disabled 枚举后单项通过，总计 74 项通过。没有为了汇报重跑已通过的 73 项。
- OAuth 定向 14 项通过；真实 React 浏览器首先复现保存双击 2 次请求，修复后 6 组通过，覆盖两来源、同号隔离、保存回读、失败保留、越权回退和低分查询。
- 浏览器阻断所有真实 API 和外部网络；仅合成 adapter，pageErrors=0，unexpectedRequests=0，productionWrites=0。不能替代真实企微或门店人工验收。
- 后端在 network=none、只读源码、512 MiB/0.7 CPU 的新临时容器执行，SQLite 内存数据；未使用生产容器/数据库跑测试。前端固定依赖 lock SHA 与既有缓存相同，类型检查在512 MiB/0.6 CPU约束下运行。

## 运行与局限
通知开启前必须明确新增通知接收范围和是否发送一条合成验收消息。只有 API 回执能确认受理，实际送达由店长企微现场核对。跨重启可靠补偿仍未实现，超时不盲重试；后续若增加 outbox 另行确认数据库。

## 证据位置
服务器 `output/takeover-feedback/`：backend.log、backend-revoked.log、frontend-unit.log、typecheck.log；本机 `output/playwright/takeover-feedback-20261026/` 保存红/绿浏览器报告与截图；`output/takeover-20261026/` 保存 #398 GitHub/生产验收结果。所有截图和测试数据均为合成。

## 最终隔离验证补充
- 后端 74 项（73 首次通过 + 修正合成状态后 1 项复验）；OAuth/操作记录中文投影 19 项；真实组件浏览器 6 组；最终 TypeScript 通过。
- hxy 构建在分配的 768 MiB cgroup 上限被终止，未影响生产。依既有授权将 131 个源文件打包到本机只读构建快照，归档 SHA256 `2dbc4b35e1992a43b4a5478145134b56a9b78fdfbb012f24449204c0cc985146`。依赖 lock 规范化 LF 后 SHA256 `69c25ee795db505939abf8a0e574e9a998c14443288b4759b5c2dcaf18a4dd88` 与既有缓存相同，无安装或升级。
- 本机 Vite 构建通过（34.28 秒），heap 上限 768 MiB、working-set 中止阈值 1280 MiB、峰值 874 MiB，低优先级及双逻辑 CPU 限制；构建后 131 个源文件逐一哈希未变。仅有既有大 chunk 提醒，不代表构建失败。没有把构建产物发布到生产。
- 企微真实测试卡及新增通知启用已集中请求明确授权；授权前保持默认 false，不发送真实消息。
