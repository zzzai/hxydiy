# 报告中心品牌界面发布：2026-10-15

任务：`REPORT-CENTER-BRAND-20261014`。状态：已生产。唯一工作流成功后，2026-10-15 11:45:08–11:45:12（Asia/Shanghai）一次只读安装/公网终验11项通过、0失败，实际current前后均为`github-87fbff8afa50-38677354836`。真实微信及门店现场另列验收。

## 已确认范围

- 复用现有透明荷叶帽IP，白底双列品牌页头；检测时间采用14px常规灰色字，不使用大号数字。
- 保留“查看报告”主操作和原生历史报告展开；公开菜单入口改为“DIY 定制我的项目”，辅助文案“按喜好搭配，选适合自己的项目”，整行可点击。
- 仅两个业务源码文件：`diy-web/src/components/ReportEntryPage.tsx`与`diy-web/src/styles.css`，提交38行新增、21行删除。源SHA256分别为`920b8d8e6a1ac4da7199fb33c11d5f9029eb111a35dfc3fc835d56422e199994`、`fedf650b69e4b79261f94a5cf7b31d384b2bfb14d9d6ba5794f81217005920a6`。
- 既有IP `assets/seat-entry-ip.png`的SHA256为`44f944293898839fc411c0007b5840b98734f5f87a9dc8e13cca5d2927bf33a3`，没有重新生图或更换资产。
- 不改报告/API/本人身份及v2记录、登录和原站返回行为、菜单链接、价格、支付、QR、权限、数据或数据库；不夹带总部看板、个人报告或面部原图新访问能力。

## 本地、合并与精确产物

- 用户确认最终本地可点击手机预览；四宽度与代表性状态既有证据保留。最后两轮仅验证时间字号及DIY文案对应窄范围，不重复有效完整验收。
- 最终生产构建退出0；27项报告相关测试通过、无失败或跳过；独立源码审查无阻断项。主包大于500kB的既有构建警告保留，不据此扩大重构范围。
- [PR #269](https://github.com/zzzai/hxydiy/pull/269)，候选HEAD `6f8d3fbf91888fbe77057915d34d94c50808294f`，合并/发布SHA `87fbff8afa506fab6beac09e9142b03ad69cf3a9`；候选与合并Git tree均为`18e55704e69a7fd422f09c6509b15740def465c1`。
- 精确main push [CI 38589195554](https://github.com/zzzai/hxydiy/actions/runs/38589195554)成功。customer artifact `11907495270`，摘要`sha256:c2a33d038562549c86c1e3a66107a696a32bba2e0b71c4b6090d16f75701eb49`；admin artifact `11907475289`，摘要`sha256:a1c93c0b9eaaea71ac161811bfbbe061f198ddd60e81d7de57d71efb347e6067`。派发前重新核对身份、摘要、未过期与当前main，不重构或重跑有效业务测试。
- 两正式ZIP完整流与真实展开体积已经核对；展开、继承静态资产及原保守峰值加3GiB储备门禁复用，不以ZIP大小冒充安装峰值。

## 容量恢复与唯一生产派发

- 昨日发布前容量被新增远程开发工具占用拦下，未发送生产POST；没有通过降低阈值继续发布。随后在明确授权下仅处理一个已备份可恢复旧工具，释放约670.3MiB，详见[容量恢复记录](capacity-recovery-20261015.md)。业务版本、数据库及备份未清理。
- 2026-10-15 11:38:57（Asia/Shanghai）即时门禁：current仍`github-d9b4e520675c-38550544089`且前后相同，可用5,826,404 KiB，要求5,783,552 KiB，余量42,852 KiB；继承assets 38,176 KiB，无两部署锁占用。锁快照不是获得锁，正式工作流仍自行持有两把锁保护。
- 仅一次POST，时间`2026-10-15T03:39:01.124743+00:00`：[Deploy Production 38677354836](https://github.com/zzzai/hxydiy/actions/runs/38677354836)，attempt1，目标为上述87fbff8a完整SHA。未知POST回执不重复，等待器只读精确run和时间窗口。
- 本机OpenSSL传输异常时改用同一代理、保留证书校验的Windows系统TLS路径；不改全局代理、Git或证书配置，不把凭据写入参数、报告或仓库。

## 实际部署与终验

- 精确工作流completed/success；实际`Backup, rehearse, deploy and verify` job `116233934506`成功，`Upload and run guarded release`于11:39:24–11:40:27（Asia/Shanghai）实际成功，非skipped。唯一等待器终态报告SHA256为`18475f33f6935bccc01a73a642da088dff7e11209a9729f8b993c9b9bb1fd9de`，由总控独立核对完整身份和步骤。
- 实际安装`/root/hxy-diy-20260811/releases/github-87fbff8afa50-38677354836`，完整MANIFEST455项通过，MANIFEST SHA256为`b2d52ad0caca6972c11d40eaa437bb2ef39322002c075028735d698d5475ded9`。旧拒绝版#268没有单独发布，当前为用户最终确认的组合。
- 未变后端`admin_v2.py`与`selections.py`的安装和实际运行容器SHA分别仍为`059bb8e560aa599fd345335711ab426f6248e041c0ac7e598288d1b8abf4f872`、`c5f41471f13017f7b4f949fb86ff521cf77d118e8ff776f9080dae563327e11b`，与精确Git blob一致。API/DB/网关运行，DB健康；不冒称API/网关另有Docker healthcheck。
- 公网health为`ok/production`；三端匿名HTML200。公网HTML引用新主JS/CSS，主模块可达新报告懒加载包；四项安装/公网SHA完全一致，且与本地最终产物/既有IP记录一致：

| 文件 | SHA256 |
| --- | --- |
| `/assets/index-CaBYUK5d.js` | `ddb88638a4e6fde41d89b4dc7dd33758eec2595959ba8dbf5a9eb8305053ec8d` |
| `/assets/index-DBWyD2HB.css` | `0a1bddd4aaf22d6fbde252ababffe4f4c049df8dc23501dcd11ed4299b342a99` |
| `/assets/ReportEntryPage-_C0XBEZz.js` | `22ec6cce6bfd0d2ac07d86e7cf733bc85997e72de95a5dc68eb170cedd149bf2` |
| `/assets/seat-entry-ip.png` | `44f944293898839fc411c0007b5840b98734f5f87a9dc8e13cca5d2927bf33a3` |

新报告包中已确认四条文案及新CSS日期14px规则；本项是有效载荷核验，不冒称真实微信视觉/本人报告验收。

- 新备份`pre-github-87fbff8afa50-38677354836-20261015T034012Z.dump`，682,082字节，时间晚于dispatch，侧文件记录SHA256为`d5000cf5418ed1b5dda690666cf450bff4c46d0fd43a4ae710a0ec2815854df4`。终验只查stat及校验侧文件元数据，未读dump、下载、重算或另做恢复。
- 本次成功发布输入自动收尾，incoming/workspace均不存在，安装release保留；终验没有执行清理。发布后可用5,737,888 KiB，约5.47GiB，磁盘86%、inode26%，高于3GiB发布后储备，两锁无持有者；容量仍预警，下一次发布仍须重新通过原容量门槛。
- 后台只读终验报告SHA256为`591b8a9bb69af0f532364fa9c214780f4faf71e0835b529e837d8ac28eccb400`，原始`server.json`为`7f4f6e449c404fcdcc92aa739292ba5ce887f96e808ccd1c2a2282c5ac0880ae`；总控核对了11项、精确SHA/run/current、资源和失败列表。证据位于后台ignored `output/report-center-brand-postdeploy-20261015/`。

真实微信手机号登录、报告原站及返回、门店现场另列验收。本批不发送真实短信、不读取实际顾客报告/照片或新增授权，也不修改企微欢迎语。事实补录只合并文档，不再次部署应用。
