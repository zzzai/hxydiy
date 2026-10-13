# 报告专用入口与登录页精简生产记录

正式版本核验报告时间：2026-10-13 23:39:58（Asia/Shanghai）；同轮交接已核验生产匿名入口。发布负责人：总控；业务实现负责人：顾客端。

## 已核验结果

- 专用入口：`https://diy.hexiaoyue.com/?store=1&view=reports`。
- 短信登录的“登录并查看报告”动作后直接进入最近一次有效原报告；有效会话和v2记录可直接进入。仅旧/缺失/撤回v2记录的已登录会话保留同页一次明确查看动作，不新增短信、勾选或独立授权页。
- 登录首屏移除三段系统实现说明及重复授权解释；保留一次“仅查看本人报告”，完整原有v2说明默认折叠、可键盘展开。未修改notice全文、版本、API或报告访问范围。
- 报告缺失、日期不确定、原链接缺失或无效均展示真实错误，不猜测来源或自动打开较旧报告。换号、失效及退出会取消旧动作；同页跳转、返回防循环和刷新直达沿用已验证逻辑。
- 原`view=return`、服务号`view=menu`、QR/座位/选单、价格及后台/技师端保持原逻辑。本次没有修改企微自动回复或美管加消息回调。

## 版本和发布证据

| 项目 | 已核验值 |
| --- | --- |
| 业务PR | [#263](https://github.com/zzzai/hxydiy/pull/263)，HEAD `7784e2e6d5e27fc89e9cd3fa854b4c16a1dcab81`，合并 `0a8997fa18f7529f95b3ff38d66bc5f1615ddce4` |
| 首屏精简PR | [#264](https://github.com/zzzai/hxydiy/pull/264)，HEAD `ad747a68b118a48a24c0b4f7ca05e08270ac4241` |
| 合并和发布SHA | `6b139f8f9a5dadbe99beb67af705a75d6c8f7d12` |
| 精确main CI | [38420629981](https://github.com/zzzai/hxydiy/actions/runs/38420629981)，success |
| 唯一正式部署 | [38421212461](https://github.com/zzzai/hxydiy/actions/runs/38421212461)，success |
| 实际发布job | [115378815730](https://github.com/zzzai/hxydiy/actions/runs/38421212461/job/115378815730)，success，`Backup, rehearse, deploy and verify` |
| 已安装current | `/root/hxy-diy-20260811/releases/github-6b139f8f9a5d-38421212461` |
| 公网健康 | `ok/production` |

服务器安装文件和公网实际下载内容SHA256一致：

| 公网文件 | SHA256 |
| --- | --- |
| `/assets/index-CZr-Opdi.js` | `ac0ffe92d141f438246c3e25885763e0fc4e190cac39e39ba877f367ae36f706` |
| `/assets/index-YY8dzw7y.css` | `a5ecc5da0a11b53c6725b470afc647f762ee46a872505e5164d575ccc886f2c6` |
| `/assets/ReportEntryPage-kc763kGi.js` | `2bb4afa10f79c6cdc7afc108a1ac4e57219fcf88522887b6c2fd4118a321abcc` |

发布仅dispatch一次。读取原run进度时本地出现`URLError`，随后不带dispatch参数恢复等待同一run，取得成功结果及实际安装核验。没有再次触发发布或重跑工作流。

## 验证边界

- #263：24项专项、5项真实组件生命周期回归及直接/短信/StrictMode/换号/返回/刷新检查有效；之前全量269通过/1既有跳过只作为有时间边界的旧证据，不冒充最终全量重跑结果。
- #264：类型检查、构建、一次窄范围detector与独立代码审查通过；375/390手机默认折叠、全文展开、键盘开合及错误提示不挡CTA通过，补一张干净初始表单截图，无新业务修改。
- 生产匿名浏览器实际页面显示精简手机号/验证码表单和默认折叠说明。未发送真实SMS、登录顾客账号、选座、提交选单或读取真实报告/面部照片。
- CI、安装哈希及匿名页面不替代微信真机、真实检测手机号到原报告的现场验收。无数据库结构、凭证或总部/员工访问范围变更；已安装历史版本、数据库和备份保留。

本地精简证据：顾客端隔离工作区`output/report-login-distill-20261013/source-state.json`、`browser-checks.json`及`screenshots/`；总控`output/report-entry-direct-release/production.json`（原网络等待失败）与`production-resumed.json`（同run恢复成功）。以上输出不含真实报告或手机号，不提交构建缓存或截图到业务源码。

## 运营交接

企微加好友自动回复已存在。只需将欢迎语中的`?store=1&view=return`替换为`?store=1&view=reports`；本次没有替用户写入企微配置。保留“用检测时的手机号登录查看”这一提示。

文档只补录已发生事实，不再次部署。现场仍需一次微信验证码登录到真实原报告的确认。
