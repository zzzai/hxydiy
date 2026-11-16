# 智荟宝会员同步：普通程序定时运行

本工具在本机专用 Chrome 中通过正常查询页面采集紫薇壹号店会员卡，再通过服务器受控新增入口处理新卡。正常运行只有 Python、Playwright、SSH 和 Windows 任务计划程序，不调用 Codex、DSH 或其他模型。开发与异常人工分析不属于零 token 运行。

## 业务边界

- 固定 tenant 1581452、shop 1581453、DIY store 1、source `meiguanjia_export`、store_code `hxy-anyang-ziwei-001`。
- 原始业务 card_number 保留全部字符，以 SHA256(store_code + U+0000 + card_number) 判重。现有卡不覆盖、不删除；旧卡余额或日期精度变化不产生新增候选。
- 两轮完整分页，核对总数、唯一卡号、门店、全手机号、原开卡日、原到期日。储值卡无期限必须有详情明确“不限期”。仅新候选保留完整手机号，私有证据不进入 Git。
- 用户 2026-10-25 的长期在用确认逐批绑定新快照、核验日期和 SHA；不把核验日期写成新用户确认。来源停用、退卡、挂失等反证立即停写。
- 复用原受审 `import_member_card_batch.py`，LF SHA256 固定 `3f30e71c3909725e255d8ae7c41362e8f65938cbef384062261dc0c9faf23925`。核心导入器版本、当前保护基准、上批审计、候选归属、预览、真实备份、隔离恢复、提交前复核、一次事务和重复只读预览全部保留。
- 当前用户、卡片、钱包及六类财务表保持保护；新增无关注册用户只能在旧行不变且候选手机号零交集时纳入基准。新出现的登录差异或新注册账号交集停写，不自动豁免。
- 首次接线精确验证 11/13 已授权状态的原文件 SHA、两项登录字段差异、原 15 卡身份及原有唯一账户匹配；没有重放 11/13 manifest，也不将该授权扩展为未来通用例外。成功后以本次新增后的完整保护基准接续。
- 不采集消费历史，不刷新已有余额快照，不部署应用或清理服务器。

## 专用浏览器与定时任务

使用 Playwright 自有浏览器进程的私有管道，无 TCP 调试监听，无现有浏览器配置复制，无 cookies/storage_state/网络响应导出。Chrome 沙箱开启。登录只保留在当前专用会话内。

`session.py` 持有单个浏览器。Windows 任务 `HXY-MemberSync-Controlled` 每天本机时间 10:00（本机配置为北京时间）及用户登录时发出固定同步请求。请求仅包含 UUID、固定动作和程序包 SHA，不能执行任意命令。另一个进程持有浏览器时，只发送请求，不启动第二个采集者。

电脑必须开机、联网并登录 Windows；专用 Chrome 会话必须有效。重启、关闭 Chrome 或源登录失效时会停止并通知，需要正常重新登录。程序不会保存密码、输入验证码或自动恢复认证。重新登录后从“顾客 → 会员卡查询”进入，仅选择紫薇壹号店，清空搜索并使用每页15条。专用窗口只保留该查询页；其他营业看板或分析页面可能持续发起请求，影响来源页面稳定等待。异常保持锁定，修复后按下节精确确认失败运行。

首次只读运行与实际计划任务验收分别记录在 [操作回执](../../docs/release/evidence/member-sync-zero-token-20261115.json)，不能把合成测试、注册成功或任务退出码单独当作同步完成。

## 程序包与运行证据

业务源码在服务器隔离工作区修改、测试和提交。`build_runtime.py` 从干净精确提交创建服务器私有不可变运行包；`package.py` 创建本机包并绑定服务器运行包 SHA。每次运行校验外部固定的 manifest SHA 和所有包内文件。

本机受限目录 `hxy-diy-private-operations/member-sync-agent/` 保存：

- `state.json`：异常锁定；`report.json`：最新脱敏业务结果。
- `request-result.json`：请求 ID 与实际采集/新增结果，不以计划任务退出码替代它。
- `owner-status.json`：浏览器进程运行状态。
- `runs/<run_id>/`：本批最小源证据、候选、只读报告和经逐文件 SHA 核对的服务器回执及备份。

服务器在对应受限 `member-sync-agent/batches/` 记录全链路；`continuity.json` 仅在旧资料保护和零新增重放预览成功后推进。来源无新增时不调用导入器。

## 异常处理

首次失败请求一次 Windows 桌面提醒并落盘报告；锁定后不反复通知、不继续写入、不自动换请求键。系统静音可能影响弹窗显示，报告是持久事实。没有发送企微、短信或外部营销消息。

采集时间若仅领先服务器 5 秒以内，服务器最多等待一次，让真实时间到达后仍执行原有 `0 <= age <= 7200` 检查；更大时差、等待后仍未来或过期都停写。不会修改来源时间戳、受审导入器、现有失败锁定或重试未知写入。

纯只读采集失败在根因修复后，可以使用 `runner.py --acknowledge-run <精确run_id>`，仍须程序包 SHA 和受限目录检查。该入口只接受只读失败，不能解除未知生产写入结果。受控新增失败必须先查同一批审计和回执；不得创建新批盲目重试，也不得清除服务器锁定掩盖问题。

备份/恢复最低资源门槛和旧行保护不放宽。恢复仅写独立演练数据库，生产不迁移、不更新旧表数据。

## 验证

```bash
python3 -m unittest discover -s tools/member_sync -p 'test_*.py' -q
python3 -m compileall -q tools/member_sync
python3 tools/member_sync/browser_smoke.py --chromium <isolated-test-browser>
```

合成浏览器测试仅用虚构会员并阻断外网，覆盖外层 SPA 地址、隐藏门店选项、完整分页及零手机号确认保存。真实来源、生产一次新增、实际计划任务分别验收。


## Member financial observations

`financial_collector.py`, `ledger_collector.py` and `payment_collector.py` use an independently authenticated background Playwright page and normal read-only UI controls. They are not attached to the existing new-card timer. Never copy browser authentication state or operate the OS mouse/keyboard.

`finance_packet.py` compiles cross-checked evidence into an exact append-only packet. `finance_controlled.py` is a coordinator-only, SHA-bound backup/rehearsal/apply entry, with one-attempt receipts. It does not migrate tables, deploy the application, alter old rows or enable unattended historical imports. Unknown refunds/payments cannot become verified savings. Inputs and backup artifacts belong in the restricted private operations directory outside Git.
