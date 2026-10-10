# 不选沙发查看本人报告入口发布记录

日期：2026-10-10（Asia/Shanghai）
任务：`CUSTOMER-SEAT-PAGE-REPORT-ENTRY-01`
状态：`Deployed`，微信现场验收待用户确认。

## 结果与边界

- 用户选择第3张：在初始沙发选择页底部新增白色常驻操作区，提示「查报告，不用选沙发」，深绿圆角按钮「查看我的检测报告」。
- 服务号无seat入口：`https://diy.hexiaoyue.com/?store=1&view=menu&source=service_account`。
- 复用现有本人报告模式、手机号登录与独立健康数据授权；没有选择、占用服务位或创建选单。实际服务位编号、排序、二维码、菜单价格、会员权益和原服务号弹层均不修改。
- 手机短屏内容留出固定底栏和安全区，不遮挡最后一排。

## 合并与生产

- 顾客端PR：[244](https://github.com/zzzai/hxydiy/pull/244)，完整HEAD `fb8a9f6812fbe0dd8df5823a05ab102a12334f57`。
- 合并主干 `adbc6f887f5ef12765970fdb29badaec230c6534`。
- 主干CI：[38062944356](https://github.com/zzzai/hxydiy/actions/runs/38062944356)，成功。
- 正式部署：[38063108772](https://github.com/zzzai/hxydiy/actions/runs/38063108772)，成功。
- 当前release `github-adbc6f887f5e-38063108772`，MANIFEST通过。
- 安装文件与公网资源SHA256一致：
  - `/assets/index-BYeIiCLT.js`：`5505c69e83d50265b384400241eada52af4bab0e45cfe0d0cdb7d4804ae6d93e`。
  - `/assets/index-2e3i-6_d.css`：`cff6a6918935c1fa2e8ecdffaddf5ab06a7138b05febf62abb383a55a9e5034a`。
- 实际bundle包含新入口文案，CSS包含固定底栏、白底和内容安全留白。

## 验证

- 22相关前端合同测试通过，全量250通过/1既有跳过，生产构建与diff检查通过。
- 375/390×844/568×匿名/已登录，共8组实际组件检查。隔离合成测试身份/服务位，不读取真实顾客报告；有效本人授权可查看，匿名401、撤回403、他人报告404，未勾选授权不能继续。
- 无选座、占用或选单请求；最后一排可完整滚动、无横向溢出与控制台错误，浏览器回退正确。
- 生产IAB390×844：无seat参数、8个既有服务位、底部按钮可见；点击直达报告手机号登录模式，浏览器回退仍在无seat选座页。没有输入手机号/验证码、提交授权或读取生产报告列表。
- 健康接口200，匿名报告与授权接口401，TCM私有源公网404；这只是辅助检查，不替代实际UI验收。
- 顾客端本地证据：`diy-web/output/playwright/customer-seat-report-entry/`，根 `design-qa.md`记录设计对照通过。
- 总控本地证据根：`C:/Users/gaoji/.codex/worktrees/token-budget/hxy-diy/output/seat-report-entry-20261010/`，含 `deployment.json`、`production-verification.json`、`production-ui.json`。
- 实际视口截图：上述目录 `production-seat-report-390-viewport.jpg`。先前 `production-seat-report-390.jpg`全页导出遗漏固定层，不作为底部按钮视觉证据；重新取得视口截图确认可见。
- 用户现有浏览器页及会话未动；仅关闭本次临时页并恢复视口设置。

## 发布前容量恢复

- 原3GB门禁保留：可用空间3134844KB低于3145728KB，未在门禁不满足时发布。
- 一次性选取10个超过48小时的旧重复上传归档；对应已安装release存在且MANIFEST通过，排除current、符号链接及未通过校验的归档。
- 全部10个归档和校验文件先复制到本地 `recoverable-upload-backups/`并核验SHA，再只移除远端对应归档/校验文件。没有递归删除，也未删除已安装release、数据库、数据库备份或其他项目。
- 移除归档117104094字节，校验文件1050字节；恢复可用3249156KB，满足原门禁。可从本地备份恢复归档；本地备份持续保留，不自动清理。
- 审核指纹 `84cd518461293a045cc845ee8d233867ce7c7f59f93a68e1b82a6f39a48240ec`，详见 `upload-space-plan.json`及`upload-space-recovery.json`。
- 未校验的旧 `github-c76ac301efa0-35576431361`归档跳过，未修改。本次不是新增服务器保留策略。

## 交付状态

本地、合并、正式发布及线上匿名导航验证完成；真实微信从服务号菜单点击新入口仍待用户现场确认。无生产业务数据写入、迁移、自动关注或真实健康报告读取。文档补录仅更新共享事实，不再次部署。
