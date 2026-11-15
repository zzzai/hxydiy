# 智荟宝会员同步：零模型只读试运行

## 当前交付状态（2026-11-15）

- 服务器独立工作区：`/root/hxy-diy-development/member-sync-zero-token-20261115`。
- 已实现只读生产索引、两次完整 UI 分页采集、新卡详情核验、脱敏报告、失败锁定、通知适配及 Windows 定时任务安装器。
- 21 项纯规则/运行器测试通过；隔离 Chromium 使用合成 16 卡（15+1）跑两遍，通过，零确认保存点击，零外部请求。
- 生产探针实际运行于 `REPEATABLE READ, READ ONLY` 事务，现有来源卡 102 张，业务写入 0。只输出 source_key，不读取全量手机号。
- Codex `automation-2` 已暂停。新 Windows 任务**尚未注册**，桌面通知**尚未真实设备验收**。
- 用户已授权专用 Chrome 连接，但运行环境仍拒绝启动命令。没有创建该连接，未取得独立程序的真实全量来源验收。
- 当前 IAB 正常查询显示 126 张卡，仅作为 UI 结构发现；不是完整新批快照，也不代表已有 25 张可导入。
- 本工具**没有 apply 功能**，不能新增会员、覆盖余额、刷新余额快照、变更学习/订单等数据。受控新增接线必须等真实只读验收通过。

## 为什么正常运行不耗模型 token

任务直接运行 Python + Playwright + 只读 SSH 查询；不经过 Codex、DSH、聊天、MCP 模型代理或云端 AI。Windows 任务计划程序负责时间；普通代码负责校验。开发和人工请求 AI 排障仍可能消耗 token。

用户需要让电脑处于开机且已登录状态，并保留专用浏览器中的正常智荟宝会话。不会自动输入密码、解验证码、复制现有浏览器凭据或导出 storage state。会话失效即锁定停止。

## 固定业务范围

- tenant=1581452、shop=1581453、DIY store=1。
- source=`meiguanjia_export`、store_code=`hxy-anyang-ziwei-001`。
- 原始业务 card_number 保持每个字符；不 trim、不补零、不使用 record_id。
- 判重为 SHA256(store_code + U+0000 + 原始卡号)；现有卡全部只读。
- 新卡只支持已审范围的年度权益卡和储值卡。原始日期采用 date_only / UTC+08:00；空到期日必须有详情明确“不限期”，不得猜测。
- 绑定 2026-10-25 用户长期在用确认及本次核验日期、源快照 SHA。核验日期不冒充新的用户确认。
- 来源明确停用、退卡、挂失、注销、冻结，或身份/门店冲突，立即停止；历史缺失旧卡不会被删除，旧余额变化不会进入写入候选。
- 只有新候选读取完整手机号。只点与当前原始卡号对应的唯一顾客链接；同名/多链接不猜测。手机号弹窗只读、取消；绝不填写或点击确认。
- 两次完整页序、总数、唯一键集合一致；所有新卡的电话、原卡号、期限、余额及归属一致。中途变化不自动重试。

## 文件及报告

`runner.py` 的命令只支持只读运行和人工解除一个精确的失败锁定；不存在 import/apply 开关。

```text
private-root/
  state.json                       # failure latch
  report.json                      # redacted latest report
  runner.lock                      # one owner
  runs/<UTC-and-random-id>/
    report.json                    # redacted
    source-private.json            # minimal frozen source
    index-private.json             # hashes of existing source card identities
    candidates-private.json        # new cards only; private phones
```

私有根目录必须在 Git 之外。Linux 使用 0700/0600；Windows 安装器只接受当前用户、SYSTEM 和 Administrators 的访问授权。不要将手机号、原卡号、浏览器资料、截图或 HTML 快照提交 Git。采集器不会存浏览器凭据、完整页面或网络响应。

错误报告只使用固定错误码和异常类型；不写浏览器/SQL 原始错误文本。首次失败记录后请求一次 Windows 托盘提醒（不发外部消息，也不唤醒 AI）；后续日程只返回 blocked_latched。系统通知被静音可能不可见，`report.json` 是落盘事实，不能把“已请求通知”说成用户已收到。

人工处理根因后，必须引用精确 run_id 解除锁定；解除只读锁不授予写入权限，也不重试未知结果的 apply。坏状态文件同样停写并报告。

## 部署前必须完成的真实验收

1. 在运行环境支持且获用户授权的专用浏览器连接中正常登录，不复制其他浏览器的认证状态。
2. 开启会员卡查询、仅选紫薇壹号店、搜索为空、每页 15 条。采集脚本严格检查已观察到的 UI 结构；布局变化即停，不调用猜测的接口。
3. 通过脚本完整读取两遍真实分页和新卡详情，与受审基准核验。确认私有文件访问范围和脱敏输出。
4. 真实验证退出登录、分页变化、身份冲突、超时、单实例、通知和失败锁定。
5. 再注册 Windows 每日 10:00 的只读任务；完成一次真实计划任务运行后才宣布替换成功。目前旧 AI 已暂停，替代任务未启用，有明确采集空档。
6. 只读通过后才开发/验收第二阶段受控新增连接；不得把合成浏览器测试当作这一步完成。

运行包生成后，先校验 package-manifest.json 的外部固定 SHA，再执行只读入口。安装器以交互登录的普通用户权限运行，不保存 Windows 密码、不创建管理员服务、不启动 Chrome、不开放网络端口。

## 第二阶段必须保留的现有导入门禁

- 复用现有受审 `import_member_card_batch.py`，LF SHA256 必须为 `3f30e71c3909725e255d8ae7c41362e8f65938cbef384062261dc0c9faf23925` 或后续正式审查版本。不得用新的简化 SQL 导入器替代。
- 本批新源、新候选、新当前保护基准、精确 manifest SHA 和状态证明全部绑定。
- 旧全行保护、来源键/手机号唯一性、普通新增账号匹配及原批审计验证；未授权的旧账号登录差异仍须停，不沿用历史某一批特批。
- 真实备份、独立恢复、立即提交前复核、部署/单负责人锁。
- 单次事务 apply，精确回执；旧用户/卡/余额/钱包/财务表保护，以及同 manifest 只读重复预览零新增。
- apply 结果未知则停并查证原回执，不换请求键盲目重试。
- 旧 15 卡暂停批次不重放；未来重新获取完整新快照。历史特批只覆盖其已核实的差异，不能扩展。
- 源消费历史、退款、余额快照刷新不在本新增任务范围。

## 验证命令

```bash
python3 -m unittest discover -s tools/member_sync -p 'test_*.py' -v
python3 -m compileall -q tools/member_sync
python3 tools/member_sync/browser_smoke.py --chromium <isolated-test-browser>
```

浏览器集成测试拦截并本地履行所有请求，只有合成会员，不连接真实源或生产数据库。生产只读探针独立验收，不能据此声称真实采集或新增已成功。
