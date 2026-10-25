# 顾客个人中心与评价返回菜单发布核验

日期：2026-10-25（Asia/Shanghai）。用户明确批准本批提交、CI及服务器验证通过后上线。

## 已核验结果

- `CUSTOMER-ACCOUNT-FEEDBACK-20261025` 已上线：[PR #384](https://github.com/zzzai/hxydiy/pull/384)，候选 `9794f9fb9db42018a6df21706a8d55b56855c681`，合并/生产 `96d26e118f1af3936e86707861607448961fd95c`；精确 [CI 40153564705](https://github.com/zzzai/hxydiy/actions/runs/40153564705) 与唯一 [Deploy 40153790913](https://github.com/zzzai/hxydiy/actions/runs/40153790913) 成功，备份/恢复演练/部署/验证 job 成功。实际 current=`github-96d26e118f1a-40153790913`。
- “我的”保留会员身份大卡片，常用入口两行三列：服务记录、待评价、检测报告、服务号、联系门店、超级星期二。服务记录默认收起；点击记录或待评价后展开对应列表并定位。服务号和周二活动使用说明弹层，沿用原活动规则。
- 独立评价成功后的“返回菜单”直达 `?store=1&view=menu&page=projects`，不再先经过菜单/报告导航页。评价失败保留输入并提示重试，连续点击有即时请求门禁，换号后不展示前一身份记录或接收迟到结果；删除了由最近50条数据推算的累计展示，没有删除历史记录。
- 生产核验 519 项 MANIFEST、169 个安装 Python 文件、3 个运行源文件和 113 个公网入口/资源哈希一致，health=`ok/production`；备份 checksum 通过，迁移集合及内容未变，后台首页与 API 主入口源文件和前版一致。本次不含数据库迁移、历史数据清理、会员/价格规则或其他未验收功能。
- 合成 React、完整 App 身份隔离测试、TypeScript/构建、375/390px 浏览器验收与必需 CI 通过；生产核验业务API调用0、数据库查询0、业务写入0。真实微信手机验收交由人员完成，不以合成测试替代。详见 `operations/customer-account-feedback-release-20261025.md`；事实文档收尾不再次部署。

## 边界与证据

- 仅9个顾客端业务/测试/PRD文件纳入功能提交；4个合成预览文件留在原工作区未提交，未作为生产入口发布。
- 后端、管理后台、依赖锁文件、部署逻辑与迁移没有变更。无充值、消费、发券、退款或外发消息。
- 本地定向24项通过、集成App身份/导航14项通过；完整顾客套件覆盖363项通过与1项原有跳过，构建资产前提和旧记录标签断言已经修正验证。正式PR与主干CI均通过全套必需检查。
- 服务器工作区 `/root/hxy-diy-development/customer-account-feedback-20261025`；本机仅哈希一致快照受限构建与Git对象中转。已有修改及合成预览完整保留。
- 本次生产 MANIFEST SHA256：`aff6c80afe9e8e90cff64ca5b466569e634032a089c858fadc77a8f6760b89ad`。
- 真实发布备份：`/root/hxy-diy-20260811/backups/pre-github-96d26e118f1a-40153790913-20261025T022329Z.dump`；SHA256 `b8d05806b2e8bb21257489cd1db0c63e3f6dcfd04175af0dc42fd5743036d5e9`，正式流水线完成恢复演练，发布后checksum复核通过。
- 脱敏回执：服务器 `/root/hxy-diy-private-operations/customer-account-feedback-20261025/`；本机 `output/customer-account-feedback-20261025/release/` 下 `deployment-result.json`、`production-verification-96d26e118f1a-40153790913.json`、`dispatch-preflight.json`、`LOCAL-VERIFICATION.md`。

## 人工现场验收

1. 微信中打开“我的”，确认本人会员卡种与有效期、六个快捷入口、默认收起的服务记录；点击待评价后能找到对应服务。
2. 门店独立评价二维码提交成功后，点击返回菜单直接到项目列表；查看检测报告仍走本人报告入口。
3. 真机键盘、网络切换与返回手势由人员观察，不标记为自动化已验收。

本文件为事实收尾，不触发新的应用部署。
