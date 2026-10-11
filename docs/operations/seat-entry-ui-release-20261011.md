# 顾客选座入口预览样式发布记录

日期：2026-10-11（Asia/Shanghai）
任务：`CUSTOMER-SEAT-PAGE-UI-RELEASE-02`
状态：`Deployed`；总控生产IAB验收通过，微信实际本人报告现场待用户确认。

## 结果与边界

- 按已批准手机预览，仅调整无seat入口：原IP和品牌区、上方「我的检测报告」浅绿卡、到店选项目标题与原座位图。报告卡说明「不用选座，登录后查看。」，查看按钮继续使用本人报告登录/独立授权。
- 主标题21px/600、报告标题17px/600、说明14px；原IP为80×84 contain，不裁切或重画。去除旧固定底部报告按钮，短屏由页面自然滚动展示最后一排座位。
- 不改真实服务位编号与排序、固定QR、菜单分类与项目内容、价格/会员、选单和身份可见范围。预览模拟接口、手机号/验证码、座位、localUiPreview及本地报告例外未进入生产。
- 原预览工作区与生成脏文件保留。业务PR只有入口组件、相关样式、原IP、两份验证脚本、设计QA和顾客workstream。

## 精确版本与生产证据

- 业务PR：[246](https://github.com/zzzai/hxydiy/pull/246)，分支 `codex/customer-seat-ui-release-02`，完整HEAD `8e64f1a82d3b45dfc91db5e221407a5e54a93e1e`。
- 合并主干 `942e1080fb6a5d4dc6ca2ea014585b32c5ae6e2c`；发布前实时确认仍为最新main，没有用旧主干产物覆盖新版本。
- 主干CI：[38104127310](https://github.com/zzzai/hxydiy/actions/runs/38104127310)，成功。
- 正式部署：[38105290034](https://github.com/zzzai/hxydiy/actions/runs/38105290034)，`Verify eligible main commit`及`Backup, rehearse, deploy and verify`均成功。
- current：`/root/hxy-diy-20260811/releases/github-942e1080fb6a-38105290034`，`MANIFEST.sha256`完整校验通过。
- 公网首页引用的JS/CSS与服务器安装文件SHA一致；原IP公网和安装文件SHA一致、原IP文件未改：

| 生产文件 | SHA256 |
| --- | --- |
| `/assets/index-IMuSCH8h.js` | `67bbce7eaaf307d30697d7419cf1f08edda02a3182d45e09d91e7c17cdf130e3` |
| `/assets/index-DpgXYxvr.css` | `15385ff5df4a9de4b0a73a0c6436603f557dfa7662d4a183f33608ab311cfc3a` |
| `/assets/seat-entry-ip.png` | `44f944293898839fc411c0007b5840b98734f5f87a9dc8e13cca5d2927bf33a3` |

## 验证与尚未验收的范围

- 本地有效验收不重复执行：`npm test`为250通过/1既有跳过，`npm run build`成功，`git diff --check`通过。
- 正式产物375/390×844/568共4组检查：无横向溢出/控制台错误，短屏最后一排无遮挡，匿名报告入口不触发选座/占用/选单或身份写入。两组正常菜单分类、加号进入详情、返回通过，真实五分类保留。
- 新文案、21/17字号、80×84 contain及无旧固定底栏在公网产物中核验；无演示数据标识。健康200、匿名报告/授权401、TCM私有源公网404。
- 未向生产创建业务选单、占用服务位或读取真实健康报告；状态/资源检查不等同完整生产UI或门店验收。总控已完成实际IAB视觉、匿名报告入口及返回检查，用户仍需微信实际本人报告现场确认。
- 本地UI证据：`diy-web/output/playwright/customer-seat-ui-release/result.json`、`output/seat-ui-release/approved-vs-production-build.png`及根 `design-qa.md`。
- 发布/只读核验报告：发布工作区 `output/seat-ui-release/deployment.json`和`production-verification.json`。
- 总控生产IAB390×844：无seat服务号入口实际加载 `index-IMuSCH8h.js`，无演示文案；报告卡y120位于座位图y315.1875之前，原IP加载、主标题21px/边距22px，8个既有沙发顺序保留。点击查看我的检测报告进入真实匿名手机号登录，返回我的再返回可回到选座页；console warn/error为空。
- IAB验收未选择任何座位、发送SMS、登录或读取健康数据。截图由总控保存于 `C:/Users/gaoji/.codex/worktrees/token-budget/hxy-diy/output/seat-ui-preview-20261011/production-final.png`和同目录 `production-report-login.png`，没有重复部署或本地测试。

## 最小可恢复容量处理

- 原门禁保留3145728KB（3221225472字节）。清理前可用3213033472字节；使用本次精确CI产物测算上传归档14642631字节、暂存工作区40603648字节（含保留旧客户assets），另留4194304字节目录/变化余量。需额外67633152字节，按已核验顺序最少选6份归档，共70318254字节。
- 每份来源为成功的正式部署工作流，archive/checksum匹配SHA，对应已安装release完整MANIFEST通过；排除current、符号链接及未验证文件。6份归档和6份校验文件全部先下载本地、核验完整SHA与校验内容，再在部署锁内重新校验路径、current和MANIFEST，最后仅删除对应12个上传文件，不删除目录。
- 每个远端删除目标为 `/root/hxy-diy-20260811/incoming/<下表release>/<release>.tar.gz`及同路径 `.tar.gz.sha256`；对应 `/releases/<release>/`全部保留：

| Release / 上传文件名前缀 | 归档SHA256 |
| --- | --- |
| `github-10e461fc37be-37924995502` | `2e65941cc743a3a167a1ee3120f50c1b3a9544f8ec18956dce6449803976bdc9` |
| `github-1c19abc5023f-37870329343` | `9d52a6dbea25d854af153822dfee3c5202456814c2bbedfcbdb6955d55eb4ae1` |
| `github-29ba37d969e8-38016240339` | `6d2015915a8a8d8922b95c228b2a14bea6c6925b4fb74488462b57dc691b33e5` |
| `github-8f7438ceba91-37946921274` | `f2e8d1c2b8a9dcbadedf0c3d4218d56dad9c3beb7d924f2fff49edae3d685190` |
| `github-93e7ca7f37c2-38024590358` | `e8e54f56d601a71c6bdc09a249aac924f54f10deca71dac5f20b0134a6c994df` |
| `github-a0ab3d82b54a-37932830848` | `ac9909def56806ce88660bdf42d62698f5ac31cf5fb8dd761d7289965e722420` |

- 完整可恢复本地备份：`C:/Users/gaoji/.codex/worktrees/customer-seat-ui-release/customer/output/seat-ui-release/recoverable-upload-backups/`，持续保留，不自动清理。
- 清单与回执：同目录上一级 `upload-space-plan.json`、`upload-space-recovery.json`；指纹 `94576e3ee0615d337ec1764f14de375a3b47213187d32fa73aadab464f86d156`。清理后可用3283177472字节，后续正常通过原容量门禁。
- 已安装release、current、数据库、数据库备份和未通过MANIFEST的 `github-c76ac301efa0-35576431361`包均未清理；不是新增长期保留策略，没有宽泛目录删除。

## 网络中断与交付

- CI产物下载连接中断后采用有界分段下载并校验ZIP，不向签名存储地址转发GitHub凭据。
- 部署dispatch已成功后状态读取中断；只恢复同SHA的已有部署等待，强制已存在run才能继续，未重复dispatch或自动重跑。
- 辅助只读核验脚本修正IP引用检查：IP由bundle引用，不要求直接写在HTML，也不按JS断言检查PNG。产品代码未因此改变。
- 文档补录分支 `codex/customer-seat-ui-release-record`只记录已核验事实，不触发第二次生产发布。生产IAB通过已在后续文档补录，微信实际本人报告现场仍待确认；不将本地构建或健康状态算作现场通过。
