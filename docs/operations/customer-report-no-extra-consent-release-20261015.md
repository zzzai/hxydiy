# 本人报告免重复授权：2026-10-15 发布记录

任务：`CUSTOMER-REPORT-NO-EXTRA-CONSENT-20261015`。本记录与会员数据导入分开；会员结果见 `member-sync-zhb-production-result-20261015.md`。

## 交付边界与顾客路径

- 用户确认检测时已授权，顾客查看本人报告不再增加 DIY 授权页、勾选、原检测授权证明或 v2/active 记录门禁。登录和报告读取不创建、补写、升级或删除 consent/audit；历史接口仅兼容，不再决定读取权限。
- 企微自动回复的既有 `https://diy.hexiaoyue.com/?store=1&view=return` 保持可用，与 `view=reports` 承接同一报告任务。未登录时用检测手机号验证码登录并查看；当前有效本人会话不重复登录，进入后打开严格校验的最近一次完整报告。Back 回报告中心，不自动循环打开；历史和再次查看均为显式操作，DIY 入口继续可达。
- 保留有效顾客 JWT、当前登录版本、当前手机号短信证明、来源 `phone + report_no` 归属及原站 URL 双重白名单校验。门店参数不代表身份；跨人、员工及无效会话仍拒绝。换号、退出和迟到响应隔离保留，菜单、签名 QR、占用和选单语义不改变。
- API、OpenAPI 与独立只读来源的报告编号统一 ASCII `[A-Za-z0-9_-]{1,128}`。不猜造原站链接、不改开旧报告、不 iframe 或预加载，不向原站传递手机号/JWT/读取密钥。后端向内部只读来源传递已验证手机号仍按原契约执行。此批不包含总部、他人报告、面部图片、下载或营销用途扩张，不包含技师 PR #271。

## 代码、CI 与已接受验证

- 业务 [PR #272](https://github.com/zzzai/hxydiy/pull/272)，最终候选 `7143d636564ab001c71add291d31fd8d3fe48921`，合并 `0b88c66e57639fe70ef8e5f09a10f6ddf48a5d72`。可靠 API 确认候选与合并树均为 `97c8cb162490c650bb1c14a0c52e196cd7aebf32`。
- 首次候选 `acc7b9f7b52da8bd83340a496b2677de5a8ef626` 的 CI 38707779908 在 OpenAPI 导出一致性失败，未合并、未重跑。补齐唯一生成文件的三处 pattern 后推送新提交，由新 CI 检查；不改变原运行时代码或绕过门禁。
- 精确主干 [CI 38709471700](https://github.com/zzzai/hxydiy/actions/runs/38709471700) 成功。customer artifact `11960107153`，digest `sha256:9eb29bb2a0ae8264fb3f594b53539ec49392a18dc48effae070896ed71301a29`；admin artifact `11959618424`，digest `sha256:54693b5a60eee0f72b85e0aae065e6e81c59f9451fa4a5f7d6c6e944a7c96229`。两项名称绑定合并 SHA，取证时均未过期。
- 本地后端合同 59 passed；仓库静态检查 52 run / 5 skipped / OK；顾客端定向测试 30/30、最终生产构建退出 0。独立审查关闭两个小问题，后续 OpenAPI-only 差异审查无新增阻断。
- Linux 服务器隔离环境后端合同 59 passed，独立来源升级/备份/恢复/健康失败回滚 3 passed；网络关闭、根只读、合成 SQLite，不挂生产 DB 或密钥。运行器修正后的成功证据复用，未重复套件。
- 顾客端真实 loopback H5 → FastAPI → SQLite → provider HTTP → 受控原站传输：HTTP 28/28、浏览器 17/17。覆盖无/旧/撤回/v2 记录、首 OTP 直达、有效会话、Back 防循环、历史、换号/退出/失效、非法链接、来源失败及公开菜单/签名 QR。8 个未受纯文案改动影响的行为观察复用，9 个最终源码场景补验，不宣称 17 项全部在最终 bundle 重跑。148 个 API 观察无 consent 调用，历史记录未改，无真实短信或外部客户报告访问。

## 容量清理与恢复

- 首次只读容量门禁失败，在 source 安装和网站 dispatch 前停止，没有降低预算。含来源备份/恢复峰值所需 6002344144 字节，可用 5821378560 字节，缺口 180965584 字节。
- 按用户既有清理边界预览并独立批准精确计划 SHA256 `14ac2bd1757c26f3e0e6e91b4353746ba4447e2d5be416465186b84c412cb3ec`。仅七项超过七天、非 current、无运行引用、逐文件重复且保留完整 MANIFEST 安装版本的旧 `workspaces/github-*`：`3541f050a8b6-37489296171`、`83da0f3db25f-37471148998`、`87f0ad4a4ce0-37449004632`、`9b3344dac7d1-37566548934`、`a2c1bd19219b-37465762521`、`ceb17908ed93-37458550451`、`d1f8d3fa65fa-37475635966`。
- 删除前完成离机归档：105512472 字节，SHA256 `ae145018844b56e3d144c84417345e5756aff874a86c7453c3a63f8803f2037f`；2764 文件、210 目录的内容/大小/权限/owner/mtime 与源清单一致，七个恢复树 hash 匹配。归档留在受限 `hxy-diy-private-operations/customer-report-no-extra-consent-20261015-capacity-14ac2bd1/`；服务器不额外生成归档。
- 2026-10-15 09:23:13 UTC 仅单次删除上述七个重复输入，实际释放 193978368 字节。保留对应七个安装版本并复核全部树与 MANIFEST，另有离机归档可恢复；数据库、备份、rehearsal 与业务容器未动。清理后可用 6015193088 字节，原容量门禁通过；current/API/image 未变，公网 health 200。
- 原始 `cleanup-result.json` SHA256 `9e2d0a0846a2bb85ee946d4bd399f683004378283f69a2f429ea8a5dfe6c69a0`，`cleanup-apply.stdout.jsonl` SHA256 `dff2dfd4059aefcd5c44508a50bb9560a4f91731ad64e00517ebbf4235e79739`。不将本次最小清理称为磁盘长期容量问题已经解决，不删除历史安装版本或备份。

## 独立来源模块已安装

- 2026-10-15 09:25:34 UTC 完成：旧 reader `695bbd707add456fdbae90df1122e79069bceb7a6cb5e639bece5aa507713008` → Git/LF 新 reader `ed0964494f5c9627b46fc1da5f4ea21b166b7a0d0dcfd1b1f2026b7b0e45d42b`。复用既有 `upgrade_reader.py`，预检退出 0、单次 `--install` 退出 0，仅重启 `tcm-webhook.service`，health 通过。
- 一致 SQLite 备份及独立恢复副本各 37199872 字节，均 SHA256 `975094bb07d3de505b3119c0616399cd5a5795174b4d286ce94d22447401173a`，恢复 integrity=ok；旧模块及两份数据库留存于 `/opt/tcm-ingest/data/reader-original-backup-20261015T092532Z-6f80aac24b4c4b318705c3fcd992e0c1`，权限 0600，目录受限。未恢复生产 DB、未新增迁移。
- 实际模块加载的十项合成鉴权/归属/ASCII/分页/IP 边界检查通过，临时合成 fixture 已清除；不将合成模块检查称为真实顾客报告联调。未查询生产报告、未发短信。`main.py` SHA `698ac14811f2b052033894981387582092d3e46c460e644f0e417785b1bab799`、环境文件元数据、reader 原 owner/0640 保持，旧网站身份未变。
- 原始 `source-upgrade-20261015T092531Z/execution.stdout.json` SHA256 `258547cf4c0470221b46a4b37f0e0ca2e55b13e5937000d740b1283c2f880c68`；`source-upgrade-execution.json` SHA256 `3297a0bb4efbe214e34275ab0419bc44aa9955dd16593f3c1e9231987f9c7a53`。

## 网站发布

- 唯一 [Deploy Production 38713160429](https://github.com/zzzai/hxydiy/actions/runs/38713160429) / attempt 1 成功；dispatch 单次得到 204，绑定 `0b88c66e57639fe70ef8e5f09a10f6ddf48a5d72` / CI38709471700 与上述双产物。实际 guarded release 步骤于 09:28:40–09:32:26 UTC 成功，不是仅 workflow 外层成功或仅已触发。
- 实际 current 为 `/root/hxy-diy-20260811/releases/github-0b88c66e5763-38713160429`；API 容器 `b395948d7c930d365900328e5dc73cc3e159542bb9ea0672867f8e8c8ce65673`，镜像 `sha256:4f787978517092c416c59a946691fddc8730d45f1c82615ffe7696f84efae6d7`。09:45:27 UTC 最后续验退出 0、`production_verified`，current/API 前后稳定，数据库容器未变。
- 完整 MANIFEST 457 项校验通过，文件 SHA256 `e6c348235df9977711403904c04091585964e44ea2246f416d20f767c443c6dd`；安装和实际运行容器中的 103 个后端文件均逐文件等于合并提交 raw Git blob。公网当前 HTML → 主 JS/CSS → `/assets/ReportEntryPage-BlKuSa2Q.js` 及品牌 IP 字节与安装/MANIFEST 精确匹配；IP SHA256 `44f944293898839fc411c0007b5840b98734f5f87a9dc8e13cca5d2927bf33a3`。公网 health 200，匿名本人报告 401。
- 实际新 API 镜像中五项合成访问控制通过：network=none、根只读、不挂生产环境或 DB，临时容器/目录清除。此为新镜像隔离验证，不称生产真人 OTP/报告读取。
- 保留两次验收输入失败：首次把 Windows `git archive` 的 checkout 换行转换结果当 raw Git 预期，改用二进制长度分帧 `git cat-file --batch` 后 103/103 匹配，原始 proof SHA256 `c994767c2ed4efebb2e363c21a616dd311381fbb4bfd2e334806b4719567f69a`。第二次错误要求 DIY 站点同名任意路径 `/api/tcm/readonly/reports` 返回 404，实际为 200 `text/html`；完整内容精确等于当前首页 SHA256 `ccee970497f8b8336e9ab235a795ff6dfd2fdd8add89444d59838504ae255596`，不是报告来源映射或报告泄露。仅修验收输入，未改生产/重发；已通过门禁不重复运行，只续未完成项。
- 来源真实 canonical 为内部 `http://172.18.0.1:18090/api/tcm/readonly/reports`，监听 `172.18.0.1:18090`、PID 与 active service 相同，新 reader SHA 精确匹配。原访问合同为 loopback/172.18.0.0/16、独立 credential 与验证手机号归属；安装模块十项合成含非信任 peer/伪造 forwarded IP 的 403。DIY 同名任意路径的首页回退不证明所有公网来源入口已作穿透测试，外网源服务穿透未验。
- 最后可用空间 5181919232 字节（约 4.83GiB），满足 3GiB 储备；长期容量风险保留。没有为验证查询真人报告、发短信、改业务/权限或新增迁移。
- 最终 `production-verification-complete.json` SHA256 `5004905cf96c9e0a5ca2b704ce889f0bb9df7ef45735e8cb90672f24c88e1150`；复用既过 gate 的回执 SHA256 `27ed41613a93b0438eef9704583874e96473a951120b2ccab6f9a13a3c74afff`，保留首次失败回执 SHA256 `bf524794524ee7887bbbbcdfd990a2adf10cdc2ccfa19950270663d103661ad6`。服务器最终续验目录 `/root/hxy-diy-private-operations/customer-report-no-extra-consent-20261015/final-continuation-20261015T094521Z`；本记录入主干不再部署应用。

## 证据与未验范围

脱敏原始交付索引保存在本次总控工作区 `output/customer-report-no-extra-consent-20261015/`，包含 GitHub、隔离服务器、顾客端最终证据引用和 production 原始回执；受限运维输入与归档不入 Git。提交事实必须与原始回执一致，不因文档合并再次部署。

真实手机微信、真实 OTP、真实原站 HTTPS/跨域 cookie/BFCache 实现及营业现场尚未验收。本次没有读取真人报告/面部图片、发送真实短信或改变企微自动回复内容，不把测试、CI、health 或脚本启动当作这些现场验收。
