# CUSTOMER-EXPERIENCE-P1-20261014 生产交付记录

状态：已生产。唯一生产工作流成功后，2026-10-14 18:51:51（Asia/Shanghai）一次只读安装/公网终验10项通过；实际current前后均`github-d9b4e520675c-38550544089`。不是仅据CI或工作流success判断。用户授权仅冻结P1及配套契约，不含新增业务、权限扩张或额外数据清理；现场仍待验。

## 精确版本与已完成门禁

- 业务[PR #266](https://github.com/zzzai/hxydiy/pull/266)：HEAD `58b103f40e87b96c56a36b7e94a9b422c884f53b`；合并/发布SHA `d9b4e520675c75910704ba93b3632e65b7dbbab2`。27指定文件包含19业务/测试及8共享文档；源码与合同/TEAM-MEMORY同批，ignored预览/依赖/证据未提交。
- 两提交完整Git tree相同：`6a4cfe8d0f890db34b797e9895dec9965040dc8f`；19 raw源码digest `9b6be3f0df8b6c00121dc05d75949738fcca1d647c262693035ce8532f5fd70a`，最终冻结无漂移。原本地限定验收快照见`customer-experience-p1-local-acceptance-20261014.md`。
- 精确主干[CI 38545634999](https://github.com/zzzai/hxydiy/actions/runs/38545634999)全部五job成功；同SHA admin-dist/customer-dist未过期。admin artifact11884630927 SHA256 `247621465487432bc2d8945bed70792b9b1b29331ccb0606166a9fec8ed0d2e7`；customer artifact11883509852 SHA256 `7c7172e11b9122d48b7dc0923a92021dc5991ecc50fe366a46b0145f840795f3`。真实ZIP展开体积分别3468851/13727270字节，不以压缩体积估安装峰值。
- 独立空白PG16.14/READ COMMITTED定向门禁：4场景、29实际ASGI HTTP、8实际阻塞审批线程通过。同请求并发200/200仅新增一次；相邻目标2→3各增1；乱序409后正确重试；前目标拒绝后增2一次。原revision/服务行快照不变；未读营业DB、ENV、真人或备份内容。隔离容器/网络已移除，3个准备fixture失败及临时证据保留，不作业务RED或并发通过计数；不代表全部竞争组合/吞吐。
- PG报告SHA256 `d626f2c76d46d1d0828b0f13ac8a8fad327da65762612206afcb0c94de05c9b2`；原始请求/DB数量/阻塞PID、隔离及资源JSON六artifact SHA均由总控核对。来源在后台ignored `output/customer-experience-p1-20261014/pg-revision-gate-58b103f4/`，没有重跑已有效47/132专项或build。

## 唯一dispatch与实际工作流

- 保守峰值2576MiB加原3072MiB储备要求至少5783552KiB空闲。dispatch前实时5931504KiB可用，余量147952KiB；旧current6b139、两锁内核快照空。锁快照不是取得锁，正式发布由现有并发组/两个文件锁再保护；容量85%预警保留，未额外清盘。
- 仅一次POST，时间`2026-10-14T10:34:40.791207+00:00`；[Deploy Production 38550544089](https://github.com/zzzai/hxydiy/actions/runs/38550544089)，attempt1、main/目标SHA与本次时间窗口均匹配。未知POST不自动重发，精确receipt保存在总控ignored输出。
- 实际`Backup, rehearse, deploy and verify` job115807209567 completed/success；`Upload and run guarded release`步骤实际18:35:04→18:42:01（Asia/Shanghai）completed/success。不是外壳success或skipped。只读唯一等待器终态报告SHA256 `e8324e169585b5bcbfbd53071dd1e65a83a0d3ccc81d002760c76981551cb309`由总控独立核验。
- 实际安装路径：`/root/hxy-diy-20260811/releases/github-d9b4e520675c-38550544089`，后台只读终验前后相同；服务器执行1次、10 checks全部ok/failures空。报告SHA256 `24b5200ef1bad61a46606104e5763a78bcd1cb9a4139f87994ecc868ee0e7efe`及原始server.json/delivery-evidence.json由总控核验，来源为后台ignored `output/customer-experience-p1-20261014/postdeploy-38550544089/`。

## 实际安装与公网终验

- 完整MANIFEST452项通过，MANIFEST SHA256 `61c833ad70df5495b056b5e9dcc5a97d441e465bac785c7fd0b087d914efbe22`；先有隐私/路径守卫，只读取发布文件。
- 安装树和实际运行API容器的`admin_v2.py`均为`059bb8e560aa599fd345335711ab426f6248e041c0ac7e598288d1b8abf4f872`，`selections.py`均为`c5f41471f13017f7b4f949fb86ff521cf77d118e8ff776f9080dae563327e11b`，匹配精确main Git blob。API/DB/nginx运行，DBhealthy，公网health `ok/production`；API/nginx没有Docker健康字段不冒称其healthcheck已配置。
- 公网HTML引用新主包；安装/公网SHA256一致：`/assets/index-DhKh41fG.js`=`b6e26810c61251478b7665eb8fbde56ccaeb749e48a2be8461ff1e2c9961de1f`；`/assets/index-Oa_KRiVL.css`=`523c7ccd8e4de9ad6f6340ff3c1e5f2e83fb5c9e615b0e11232099188d123921`；从新主模块可达引用确定的`/assets/ReportEntryPage-CoNbNz_b.js`=`c1516ad04fe5a11fd8c68f4a0b611d6ab641e45f1f89c65d234c64e452fcda50`，没有选旧保留lazy文件。
- 新备份basename `pre-github-d9b4e520675c-38550544089-20261014T104147Z.dump`，stat680657字节、mtime`2026-10-14T10:41:47.800440+00:00`，既有checksum记录`eb505c2088eebe8cd748e5c68cdff7ae84fa78d8366560dc255eaf303e440f49`。实际job有严格basename的checksum OK和deployed标记，结合不变的强制`pg_restore --exit-on-error`/`SELECT 1`流程证明本次恢复门禁成功；终验不读取/下载/重算dump、不重新恢复或连接营业库。
- 既有发布工具日志`cleanup=completed`，本次重复上传2文件及解压工作区移除；同release incoming/workspace实际不存在，installed release保留，未另删历史版本/数据库/备份。此次输入可由保留正式安装重建。
- 终验可用5841888KiB（约5.57GiB）、磁盘86%、inode26%，两锁内核快照空；原3GiB储备通过，但容量仍预警，不宣称磁盘问题已解决。

## 本批边界

数量/关联来源撤销、本人受控追加/同行只读、完整目标修订差量与冻结、明确报告入口/原站Back中心、旧企微return兼容已纳入。本批没有UI改版、新主图、价格/时长/支付/QR配置改变、迁移/新凭据或员工/总部报告照片权限扩张；企微欢迎语配置未修改。

历史/异常空顾客身份的技师履约展示建议未夹带实施；正式签名扫码建立匿名主体，不能从直接POST空身份fixture外推现场故障。微信/provider真实返回、真实短信登录与报告、门店营业现场仍待现场验收。发布文档补录不重发生产。
