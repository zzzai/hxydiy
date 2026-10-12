# 微信服务号菜单顶部间距修正（2026-10-12）

状态：已正式发布，2026-10-12 20:13（Asia/Shanghai）核验完成。微信真机现场待用户重新进入确认。

- 业务[PR #261](https://github.com/zzzai/hxydiy/pull/261)，HEAD`2f3a2b799e96f2f12b0c966868a78306bc8ea019`，合并/发布`4ae5135e020bb9a146da373d5446a63302820783`；精确main CI`38246243138`和唯一部署`38246760294`成功。
- 问题复现：既有菜单顶栏`max(6px, env(safe-area-inset-top))`在44安全区时使顶栏高82、我的按钮顶距44。只对微信UA的公开菜单使用6px上内边距，复用既有微信识别；没有删除全局安全区或更改viewport。普通浏览器44安全区仍保留，底部安全区、QR/已绑定菜单、个人中心/详情顶栏不调整。
- 只改App顶栏标记和两行作用域CSS，14项已还原详情、图片/文案/字体、价格/默认值/计费、服务号双入口、QR、报告/登录独立授权和后端不改；没有接口/数据契约变化。
- 本地构建通过，252项通过、1项既有跳过。真实应用浏览器复现修复前失败；本地与生产375/390×844 × 顶部安全区0/44/59各6组通过，顶栏44、我的按钮顶距6，无横向溢出。普通浏览器生产44安全区仍保留；匿名我的登录/返回通过，无console warn/error。测试使用浏览器的微信UA和安全区模拟，不声称操作了真实微信客户端；不登录、不发短信、不写选单/占用或读取本人报告。

## 实际生产

- current精确为`/root/hxy-diy-20260811/releases/github-4ae5135e020b-38246760294`，完整MANIFEST通过；API容器`33099288017a5a977a379e1bc056a8c19cc40953263d11e0f03cb349a9326d52`。
- 公网HTML与浏览器加载本次主包，JS/CSS内容SHA与安装文件相同：`/assets/index-6Bnv3kyK.js`，`f00c3534292d24e087c2712167bca24339ddcb8dcaa789480beaeeeb66b2c8ed`；`/assets/index-D7KQuJ7-.css`，`4dc00ead3119f565fb8ec0087af246f7e864a8394480b0958c8a339389bf237e`。
- 健康`ok/production`，管理/技师入口200，14项门店价/会员价与原基准一致；已撤销的详情改版标记仍不存在，预览夹具没有混入正式包。
- 本次成功的重复incoming/workspace已自动收尾；正式安装、历史release、数据库与备份保留。可用6963187712字节，原3GiB门禁不变，没有额外历史清理或重复dispatch。
- 测试专用UA/安全区模拟随测试标签关闭撤销，浏览器临时手机尺寸已重置。发布记录补录只合并文档，不再部署。

证据：`output/menu-top-gap-build.log`、`output/menu-top-gap-tests.log`、`output/menu-top-gap-release-result.json`、`output/menu-top-gap-release-verification.json`及`output/diy-first-ui/menu-top-gap/`的前后测量、普通浏览器测量、生产截图。
