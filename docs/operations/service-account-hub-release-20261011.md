# 服务号报告与公共菜单双入口发布记录

日期：2026-10-11（Asia/Shanghai）
任务：`CUSTOMER-SERVICE-ACCOUNT-HUB-01`
状态：`Deployed`；总控生产匿名IAB验收通过，微信本人报告现场待用户确认。

## 结果与边界

- 原链接 `https://diy.hexiaoyue.com/?store=1&view=menu`不需更换，无seat首页仅「查看检测报告」「进入菜单」，不展示座位图。
- 报告复用原手机号登录、本人报告范围和独立健康授权，返回首页；未改变后端API、身份/健康可见范围或授权合同。
- public-menu独立浏览真实项目分类、价格和详情，不复用后端browse_only，不恢复旧座位记录，不建立占用/选单/协作轮询；详情偏好仅临时浏览。「到店选项目」明确进入原座位核对，选座后继续原业务，不自动添加/提交。
- 显式seat QR、已绑定设备、项目分享、kiosk及原受控点单优先级保留。原IP未改，保持白/浅绿/深绿、22px边距和21/17/14px层级。未修改菜单项目、价格、会员、数据库或凭据。
- 独立实现工作区和原预览工作区保留；vite生成文件与tsbuildinfo未提交。导航合同和TEAM/customer workstream已在业务PR同批更新。

## 精确版本与生产核验

- 业务[PR #249](https://github.com/zzzai/hxydiy/pull/249)，分支`codex/customer-service-account-hub-01`；完整HEAD `a4a985e8d9d264a506491af3b0a05d5555f88bed`。
- 合并/实际发布主干 `7536c3a0e89f188f467cb192708a042c90c7a3ff`；精确[main CI 38108018553](https://github.com/zzzai/hxydiy/actions/runs/38108018553)成功。
- 唯一正式[部署38118780088](https://github.com/zzzai/hxydiy/actions/runs/38118780088)成功，`Verify eligible main commit`和`Backup, rehearse, deploy and verify`均成功。POST响应读取中断后只读查回原受理任务；退避等待终态，未重发、关闭TLS校验或更换业务版本。
- current解析为`/root/hxy-diy-20260811/releases/github-7536c3a0e89f-38118780088`；installed `MANIFEST.sha256`完整校验通过。公网首页及原服务号链接引用同一安装JS/CSS，下载文件SHA256匹配安装文件，原IP一致；不将HTTP200单独当作部署或现场证明。

| 生产文件 | SHA256 |
| --- | --- |
| `/assets/index-D00dOUcd.js` | `9d47fd1154acfeee8534b5c6e711249082413626dc574a581589a442fab3a65d` |
| `/assets/index-D6X8dnHw.css` | `8b4f2c689c191b97eff06f8be7f03a3044d87becd83c90ce447cf098f4b7a24c` |
| `/assets/seat-entry-ip.png` | `44f944293898839fc411c0007b5840b98734f5f87a9dc8e13cca5d2927bf33a3` |

- 原链接200，`/api/v1/health`200；匿名`/api/v1/me/tcm-reports`和`/api/v1/me/tcm-report-consent`仍401；TCM私有源`/api/tcm/readonly/reports`公网404。公网bundle含新入口/路由/样式，未含本地演示手机号、验证码、报告或preview标记。
- 本次仅生产部署和公开只读资源/权限检查，未创建业务会话/选单、占用服务位、发送SMS、登录顾客或读取实际健康报告。部署不含菜单应用、迁移或凭据写入。

## 已有验证与生产IAB

- 本地`npm test`252通过/1既有跳过/0失败；`npm run build`成功，`git diff --check`通过。2项导航测试先失败再通过；375/390×844/568正式构建检查覆盖三种source、旧记录不恢复、无seat刷新、报告入口/返回、5分类、加号详情和到店选座后的原流程；另有两组显式签名QR/绑定设备回归。有效验收不重复运行。
- 总控生产匿名IAB390×844原无source链接：首页仅两入口，无座位图；原IP加载，报告按钮rect x22/width346。查看检测报告直接到真实手机号表单，「返回首页」有效。
- 进入菜单到`page=projects`，真实分类/价格和现煮草本泡详情可浏览；详情「到店选项目」到`page=seats`才显示原沙发图，仅进入图未选择沙发。返回菜单reload仍无座位标签或已提交前台提示；console error/warn空，无横向溢出。
- IAB未选座、发送验证码、写占用/选单或读取报告。此匿名页面验收不等同微信真实本人报告登录/授权/阅读的门店现场验收，后者仍待用户确认。
- 本地UI证据：实现工作区`diy-web/output/playwright/customer-service-account-hub/result.json`及同目录截图/测试日志。
- 发布证据：`C:/Users/gaoji/.codex/worktrees/customer-service-account-hub/customer/output/service-account-hub-release/`下`deployment-connector.json`、`production-verification.json`、`cleanup-result.json`和`release-receipt.json`；这些本机证据不替代合并主干的共享事实。
- 总控生产截图：`C:/Users/gaoji/.codex/worktrees/token-budget/hxy-diy/output/service-account-hub-20261011/`下`production-home.png`、`production-report-login.png`、`production-menu.png`。

## 最小可恢复容量处理

- 原3GB门禁为3145728KiB/3221225472字节，未降低。按本次精确CI产物估算上传/展开/旧assets暂存及余量60063448字节；最终清理前可用3141922816字节，需释放139366104字节。
- 用户明确授权一份125570601字节npm缓存；此前授权的六份已校验旧重复上传归档仅取满足容量的最少两份，连校验文件共23430376字节。第一轮单归档预检不足时停止，未删除；最终总选149000977字节、仅5个明确文件，实际可用空间增加149024768字节到3290947584字节。
- 全部先下载本地并核验完整哈希/校验文本；部署锁内再次验证精确路径、非符号链接、无开放文件PID、current及对应installed release完整MANIFEST。仅unlink下列文件，不递归删目录。

| 远端精确文件 | 可恢复本地文件 | 核验 |
| --- | --- | --- |
| `/root/.npm/_cacache/content-v2/sha512/b9/95/da37d24fc6ed3f8e39eaa8979377891160f9e35592b732256775f1b59878446a80ca2fb49c5877cfaaf0043a3c2c48312641294c7d4926bd8a7f08772263` | `npm-cache-b995da37.blob` | SHA512 `b995da37d24fc6ed3f8e39eaa8979377891160f9e35592b732256775f1b59878446a80ca2fb49c5877cfaaf0043a3c2c48312641294c7d4926bd8a7f08772263` |
| `/root/hxy-diy-20260811/incoming/github-d1f8d3fa65fa-37475635966/github-d1f8d3fa65fa-37475635966.tar.gz` | `github-d1f8d3fa65fa-37475635966.tar.gz` | SHA256 `240d7d1829635b51de2ec566da2a8909faff9633abe8e282ce33d80d79445d8b`；11711960字节 |
| `/root/hxy-diy-20260811/incoming/github-d1f8d3fa65fa-37475635966/github-d1f8d3fa65fa-37475635966.tar.gz.sha256` | `github-d1f8d3fa65fa-37475635966.tar.gz.sha256` | 105字节，校验文本对应归档 |
| `/root/hxy-diy-20260811/incoming/github-ae2f1d6bda86-38033862332/github-ae2f1d6bda86-38033862332.tar.gz` | `github-ae2f1d6bda86-38033862332.tar.gz` | SHA256 `a81535d1dc2e150fea7dbe9269b381797d31f1c3675cacf2f03afb5e5d858c03`；11718206字节 |
| `/root/hxy-diy-20260811/incoming/github-ae2f1d6bda86-38033862332/github-ae2f1d6bda86-38033862332.tar.gz.sha256` | `github-ae2f1d6bda86-38033862332.tar.gz.sha256` | 105字节，校验文本对应归档 |

- 完整本地备份根目录：`C:/Users/gaoji/.codex/worktrees/customer-service-account-hub/customer/output/service-account-hub-release/recoverable-upload-backups/`，持续保留，不自动清理。`cleanup-result.json`记录5个source/backup映射、哈希、前后空间及2026-10-11T06:39:23.746934Z锁内核验时刻。
- 如未来获准恢复：先校验本地文件上表哈希/文本；确认精确source不存在且无在途部署，再仅将对应backup复制到其source，重新校验。不得覆盖新文件、递归清理、改变current或把旧上传包重新部署。本次未执行恢复。
- 对应`releases/github-d1f8d3fa65fa-37475635966`、`releases/github-ae2f1d6bda86-38033862332`和此前current `releases/github-942e1080fb6a-38105290034`均保留。未动其他npm/Docker缓存、Docker数据、数据库/备份、原工作区或未提交文件。

## 文档交付与现场边界

- 本记录、CURRENT-STATE、WORK-STATUS顶部及顾客workstream在总控生产IAB通过后同批补录。文档PR遵守精确HEAD CI门禁；仅合并文档，不触发新生产部署，实际current仍为上述业务SHA产物。
- 用户后续微信本人登录、独立授权及实际报告查阅结果另行记录；不凭匿名IAB、测试通过或HTTP200推定完成。
