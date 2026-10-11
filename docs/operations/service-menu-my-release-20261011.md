# 服务号菜单「我的」入口发布记录

日期：2026-10-11（Asia/Shanghai）
任务：`CUSTOMER-SERVICE-MENU-MY-01`
状态：`Deployed`；生产匿名Chrome验收通过，微信真机与本人报告现场待用户确认。

## 结果与边界

- 原链接 `https://diy.hexiaoyue.com/?store=1&view=menu`不用更换；无seat首页仍只有报告、菜单两个入口。公共菜单恢复「荷小悦草本泡脚」品牌顶栏与原「我的」按钮，匿名使用原手机号登录页，返回原无seat菜单。
- 分类、项目内容、价格、原IP不变；公共浏览仍不恢复旧服务位、不建立占用/选单或共享轮询。明确到店选项目仍走原受控选座，显式QR和绑定设备行为、本人报告独立授权不变。
- 业务PR已同批更新导航合同、TEAM记忆及customer workstream。未改后端API、数据库迁移、凭据、身份或健康数据可见范围；生成脏文件保留且未提交。

## 精确发布版本

- 分支 `codex/customer-service-menu-my-01`；[PR #251](https://github.com/zzzai/hxydiy/pull/251)完整HEAD `ddce8e7105c387c1476c5f6b34e7aca6cb9d11d6`。
- 合并/实际发布SHA `369d90a33d9120f5e2b2d207f10cd518a3df5fd9`；[main CI 38127427897](https://github.com/zzzai/hxydiy/actions/runs/38127427897)成功。
- 唯一[Deploy Production 38128752578](https://github.com/zzzai/hxydiy/actions/runs/38128752578)成功；资格检查、Backup/rehearse/deploy/verify两个job均成功，没有重复dispatch。
- current `github-369d90a33d91-38128752578`；安装完整MANIFEST通过，公网文件与安装哈希一致：
  - `/assets/index-BcOBP-YF.js`：`27cc0fe03e9d4cb07324fb2f9d339b17a66fd91b2a0003a10e3422e3445dd4e5`
  - `/assets/index-DnqNRIBk.css`：`ca7a7daa16b20cb99adab4b41afe776593d89f4a59d5921e40bd6617109a0d2e`
  - 原 `/assets/seat-entry-ip.png`：`44f944293898839fc411c0007b5840b98734f5f87a9dc8e13cca5d2927bf33a3`

## 容量与数据边界

- 原估算所需回收131173949字节，仅核验已安装版本的重复包不足；用户进一步明确授权已卸载旧版本的上传包，要求完整可恢复备份、校验后最小清理，数据库/运行版本/既有服务器备份不清理。
- 授权后只读重检服务器空间已恢复。锁内新鲜核验free=4592828416字节；原gate=3221225472字节，精确CI暂存预算60673597字节，暂存后余量4532154819字节，足够发布。
- 本次实际删除文件为0，不需要下载备份或删除旧包，也未扩大到npm/Docker/数据库/服务器备份。容量恢复原因未调查或推断。
- 发布后只读核验此前84个已安装release和23份本次核验的旧上传包及校验文件仍在；旧运行目录保留，仅正常部署切换current。标准发布流程新建备份与隔离恢复演练不等于清理既有备份或修改业务数据库。

## 验证与现场状态

- 本地有效证据无新源码变化，复用252通过/1既有跳过、构建通过、375/390×844/568四组真实组件回归；原正式构建先RED确认「我的」缺失，修复后GREEN。覆盖个人中心/匿名手机号表单/返回、报告双入口、分类加号详情、无seat刷新、明确选座及签名QR/绑定设备。
- 生产健康200；匿名本人报告与报告授权均401；TCM私有源公网404。未读取真实报告，没有身份授权或数据库测试写入。
- 生产匿名Chrome 375/390：原无source链接首页无座位，菜单正常品牌与「我的」，个人中心真实匿名表单/返回菜单、五分类、加号详情/返回、刷新仍无seat通过；无横向溢出或pageerror。真实公开API只读GET，分析事件被测试端抑制，非GET API请求拦截器未触发；未选座、登录、发送SMS或提交服务。
- 本地证据：`diy-web/output/playwright/customer-service-menu-my/`；生产截图与行为报告：`diy-web/output/playwright/service-menu-my-production/`。发布、容量、版本/权限核验：`output/service-menu-my-release/`。这是生产匿名浏览器验收，不是微信真机、真实登录或本人报告现场验收。
- 本次仅补录发布文档，不再部署。
