# 服务号弹层原图精修交付记录

## 目标与边界

- Task: `CUSTOMER-SERVICE-ACCOUNT-SHEET-02-FIDELITY`。顾客端唯一窗口实现；总控仅审查、协调与发布，不重复编写业务UI或运行有效本地测试。
- 唯一视觉源为用户附件 `codex-clipboard-598b7498-da49-4d31-9f8e-dc09dde81cb9.png`，853×1844归一390×844。纠正#240将站立素材视为可接受约束的误判；还原探头双手趴边人物、圆头像、薄荷绿提示、白色圆角弹层、主区域比例和完整浅绿搜索横条。
- 人物、头像和提示为独立透明PNG，界面文字与二维码不栅格化为整张图。服务号原JPEG保持逐字节不变；不生成假二维码、不更换店长企微码。
- 登录、报告独立授权、企微、价格会员、菜单与服务位规则不变；不修改微信后台，不执行关注、发券、通知或健康报告读取。

## 本地与审查证据

- [PR #242](https://github.com/zzzai/hxydiy/pull/242)，完整HEAD `bb24bd06c7e4ef59c4916c3ddd7fe83e674fa113`；合并 `f04def6b34424ef3fdb7592d1084d6c3240df5fb`，精确主干[CI 38045997792](https://github.com/zzzai/hxydiy/actions/runs/38045997792)成功。
- 顾客端250测试通过、1既有跳过；最终构建、diff检查及375/390×844/568四组真实组件验证通过：首页/我的入口、二维码完整及长按语义、复制名称成功/拒绝、关闭/ESC、无横向溢出/控制台异常与企微不变。
- `design-qa.md`新任务明确取代旧站立姿态验收，最终为passed。总控打开同尺寸原图与实际页面合并对照，退回缺失绿提示及字号差异；三素材/26px标题/20px主提示修正后再次打开对照。实际CDP字形为Microsoft YaHei，不仅依据CSS回退名称；保留正常平台抗锯齿差异，不将背景合成顾客伪造成源图年度会员。
- 顾客端本地证据 `diy-web/output/playwright/customer-service-account-sheet-fidelity/`，包括result.json、最终reference-vs-implementation.png与手机/短屏截图。短屏隐藏外伸装饰、辅助内容内部滚动，原二维码和关闭仍完整可用。

## 生产核验

- [正式发布38046186526](https://github.com/zzzai/hxydiy/actions/runs/38046186526)资格检查及带备份/恢复演练/安装核验成功。安装current为 `github-f04def6b3442-38046186526`，MANIFEST全量通过。
- 公网HTML引用安装资源，JS `/assets/index-CvnBac0K.js` SHA256 `79aee19c505e9a6cf836515525511eebf905355d5fae100ff4620428c2b9712b`；CSS `/assets/index-ZgJc02dQ.css` SHA256 `04eb9eb5e0a27c7c994e68ffeb46c8a740c7ab45597554191bb7619b9ddad67e`。公网与安装哈希一致，新版长按说明、底部弹层及企微说明保留，复制备用链接主按钮仍移除。
- 三个新素材的主干原文件、安装文件及公网文件SHA256一致：
  - `/assets/service-account-peeking-v2.png`：`68b22b85d848cd961b22221dffcce134c4f33f712b893910154378afbe26b939`。
  - `/assets/service-account-avatar-v2.png`：`24be572457f0b554a53028c47a761cb0a669079aef41e3b1a035b8eb2e313feb`。
  - `/assets/service-account-mint-marks-v2.png`：`c1aa17dec721f5b4e8ed156f3cf09e583fa7799b408106b48ec6a2b7fe783b2e`。
- 原服务号码 `/assets/hxy-service-account-qr.jpg` SHA256仍为 `2316315edb11d0f701f2326697a3123c85ed38b5b037e27d7f1b4e59fad6f299`。health200、匿名本人报告/授权401、TCM内部读取公网404；没有业务写入、迁移或真实健康报告读取。
- 生产IAB匿名个人页从固定回访URL打开“查看入口”；390×844实际弹层top174.94/width390，三个新素材及258px原二维码均完整加载，二维码显示218px含原静区，关闭有效。实际完整截图 `output/service-account-fidelity-20261010/production-sheet-390-full.jpg`；初次仅截取宿主可视部分的截图不作为完整视口证据。临时视口已恢复，临时页已关闭，无登录/占位/报告访问。
- 总控机器证据 `output/service-account-fidelity-20261010/{deployment,production-verification}.json`；取主干的一次网络错误已通过只读重取恢复，未重复触发发布。本次未清理服务器文件，文档补录不再次部署。

## 现场边界

- 本地与IAB渲染、原码解码、CI和安装核验不代表真实微信关注成功；微信长按识别服务号、关注及底部菜单回访仍由用户现场确认。
- 回访地址保持 `https://diy.hexiaoyue.com/?store=1&view=return`，到店选项目继续核对服务位，关注不是正常服务或本人报告访问前置条件。
