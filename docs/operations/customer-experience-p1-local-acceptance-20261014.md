# CUSTOMER-EXPERIENCE-P1-20261014 本地限定集成验收

提交前快照：本地 `Integrated`，当时业务和本文件均未提交、合并或发布。本记录只覆盖所列合成场景，不代替生产或门店现场验收；后续#266合并、真实PG补验及生产交付见`customer-experience-p1-release-20261014.md`。

此为提交前验收快照。2026-10-14用户随后明确授权本批提交/PR、必需CI后合并、服务器验证后发布生产；交付执行不增加本记录的测试覆盖，实际提交/合并/生产需另记精确证据。

## 候选与范围

- 统一工作区：`C:/Users/gaoji/.codex/worktrees/customer-experience-fixes/hxy-diy`，branch `codex/customer-experience-fixes-20261014`。
- BASE/HEAD：`bb3e57e0ad48d562e3927862c87ce8904a70e118`。实现为19个未提交源码/测试文件；HEAD本身不包含本批实现。
- 统一源码digest：`9b6be3f0df8b6c00121dc05d75949738fcca1d647c262693035ce8532f5fd70a`；逐路径SHA清单位于本地ignored `output/project-control/integration-input-manifest.json`。
- 顾客15文件digest：`4b98006c83d9de5a83e490096d2b69d102d05bdb87d2586347e6c1b1edb1ef30`；后端4文件digest：`ecce876d0557d7a0885e4e1e263b9cdeff55acdec0ccdc2050af5069697b28c3`。
- 详情保存保留数量；关联取消精确撤销来源；本人提交后受控追加、同行只读；完整目标修订按已确认单位算差量、批准锁内重算；报告明确入口/返回中心及旧企微return兼容。未改价格、素材、IP、支付、数据库、凭据或权限。

## 验证与复审

- 后端数量/来源重分类：最新47项窄回归通过；真实顾客序列化配合隔离HTTP验证完整目标B=2只新增1。更早132/27不是最新候选全量结果。
- 报告BFCache身份刷新竞态：真实组件effects红2失败→绿5通过、24报告定向通过；修正及增量复审通过。该受控renderer不是微信BFCache现场验收。
- 裸入口canonical刷新歧义：真实helper红1失败→入口11通过、noEmit类型检查通过；三文件scoped复审通过。root另用390px真实App验证裸入口刷新、个人中心报告明确动作及浏览器Back仍回裸入口，未输入手机号/OTP或打开原站报告。
- source/contracts任务与最终增量审查通过，两项Important均关闭；19个统一源码字节与交付SHA一致。未重复已有效的套件或构建。
- 最新候选`npm run build`仅一次exit0，`tests/foot-refine-assets.test.ts`仅一次/1通过。收据SHA `ef75600971f9ebd19153633a7067645eec71a8616664d006eadfbac990b2dcc4`；132产物digest `b53b6552563af87d5630f309983ad4d74eca7432b56391a2b62265904e92e50d`。Vite>500kB警告保留，不隐藏或改阈值；旧收据不覆盖、不冒用。
- 技师隔离合成库：9 API执行/9通过，验证首次2份、等待状态拒绝追加、不同/同配置净增、拒绝、提交/审批幂等及顺序审批。审批前/后任务、服务行及旧快照有实际HTTP/DB证据。
- 技师真实前端代表UI：375px的T1/T3/T4与390px的T6/T8，共5例。既有CUA轨迹及观察摘要经只读核验；不是两种宽度各九例或完整像素验收。API承担数量/冻结/幂等的强证据。

## 身份边界与未验范围

- 技师矩阵使用已绑定合成顾客。正式签名服务位入口在代码和既有测试中会建立/复用`anon_*`主体，因此首轮直接创建的空身份fixture不能证明正式扫码故障；未据此声称微信现场通过。
- 只读后续核查确认既有技师前端把当前服务单与`user_id`绑定，历史/异常空`customer_id`活动选单即使API返回items仍可能被隐藏。最小建议是当前履约按占用/选单判断，历史/画像仍按顾客主体；本轮未实施，未扩权限，也不把该场景纳入通过。
- 复杂偏好/加项、门店/同行权限沿用既有合同验证，不从九例空偏好矩阵推导新增全覆盖。
- 真实PostgreSQL并发、微信/provider原报告回退、真实短信/报告/照片和门店营业现场未验。本轮未读真人资料、生产ENV或创建生产选单。

## 交付位置

- 交付前曾发现原4199预览服务停止、原顾客/后端临时路径不可用，原因尚未确认；总控未删除或归档。统一工作区与19源码仍存在，SHA重新核验一致。顾客端已仅恢复安全合成预览，总控独立确认导览→本地合成原站报告→浏览器Back→真实报告中心；此恢复不证明原路径失效原因已解决。
- 19源码/测试与8共享文档额外恢复导出在主项目ignored `output/customer-experience-p1-recovery/candidate-1791965510373.patch`及对应JSON，27文件；只读reverse-check通过，补丁SHA `a56541374064b8636fbeb5f4cb9fd46168ba9baf9e11649689da1c5d71dff0cc`。未执行应用、提交、回滚或删除。

- 安全真实App合成预览：`http://127.0.0.1:4199/__fixture?case=first`；不发送真实短信或读取真人报告，非生产。
- 已登录合成预览：`http://127.0.0.1:4199/__fixture?case=ready`。首次登录场景使用合成手机号`13800000001`、验证码`123456`，不发送短信。报告跳转替换为同源`/synthetic-original`，返回中心可见最新/历史报告及公开项目入口。
- 恢复证据在统一工作区ignored `output/preview-restore-20261014/`：`server.mjs` SHA `442f2befd6b7c6a14231aab72bb1b6d73372b0bfb1e1fee51988a73dc5bf340a`、`report.md` SHA `777af81283e491a16d8ac003ff4789c4fd2a070d5fff12713c1c247e1306e883`、`evidence.json` SHA `84ac929cb17d9b95287d06c1bebd1ad91a68c7f4a60fd8b928bf8c84fbc8b446`；截图`report-login.png`和`report-center.png`保留。总控核验19/19源码SHA和union digest仍匹配。
- 可用性核验时仅监听`127.0.0.1:4199`，PID37368；Vite无配置/生产proxy，ENV/cache位于ignored输出，未支持API返回404，CSP限制外部连接。复用已安装依赖，无安装、business修改、重复suite/build或真实SMS/报告/选单请求。进程存活属于本次观测，不承诺应用/主机关机后仍在线。
- 精简报告/审查/浏览器记录：本地ignored `output/project-control/`；技师API JSON：`output/customer-experience-p1-20261014/technician-api-evidence.json`；技师报告在既有技师窗口对应ignored目录。
- 此提交前快照时提交/PR/合并/生产尚未执行；用户随后明确授权并完成#266及生产交付，精确后续证据在独立发布记录中。本快照不充当发布批准或当前安装事实。
