# 服务号二维码底部弹层交付记录

> 后续纠正：用户要求还原附件中的趴边人物和圆头像，不接受仅复用站立素材的近似版。此前将原IP姿态视为用户约束的判断不成立；本批视觉验收已由#242精修版取代，见 `service-account-sheet-fidelity-20261010.md`。以下保留首批发布与容量处理历史。

## 范围与实现

- Task: `CUSTOMER-SERVICE-ACCOUNT-SHEET-02`；唯一顾客端窗口实现，总控负责审查、合并、发布和共享状态。
- 用户选定第2张：纯白大圆角底部弹层，已有荷小悦IP、大原二维码、两步关注说明；取消URL框及复制链接主按钮，名称搜索/复制仅作兜底。
- 服务号 `荷小悦草本轻养` 使用用户提供的258×258 JPEG原文件，SHA256 `2316315edb11d0f701f2326697a3123c85ed38b5b037e27d7f1b4e59fad6f299`；不是生成示意码，不替换店长企微码。
- 沿用首页/我的入口、关闭记忆及焦点行为。保留自愿关注、本人登录和独立健康数据授权；不改服务位、登录、菜单、价格、会员权益、报告读取、企微弹层或微信后台菜单。

## 本地及合并证据

- PR [#240](https://github.com/zzzai/hxydiy/pull/240)，HEAD `a97592f220b772e9b2bf6806a23f4880b0626983`；合并主干 `b83174206afe0623df0c583048b55b0538c78e18`，精确主干CI [38041043713](https://github.com/zzzai/hxydiy/actions/runs/38041043713)成功。
- 顾客端250测试通过、1既有跳过；构建与diff检查通过。375/390×844/568四组真实本地组件核对：首页/我的入口、二维码完整显示、复制名称成功/失败、关闭/ESC、无横向溢出/控制台异常、企微入口保留。
- `design-qa.md`本任务`final result: passed`；源图与390×844实际渲染在同一对照图检查。真实原码、原字体及原IP姿态为明确生产约束，短屏装饰隐藏、正文内部滚动。
- 本地证据位于顾客端隔离工作区 `diy-web/output/playwright/customer-service-account-sheet-02/`，包括result.json、reference-vs-implementation.png及四组截图；不重复运行已有有效本地验收。

## 发布容量阻断与恢复

- 首次正式发布 [38041230543](https://github.com/zzzai/hxydiy/actions/runs/38041230543)失败：`CAPACITY_INSUFFICIENT: available_kb=3097980 required_kb=3145728`；容量门禁在备份/激活之前拒绝，current保持 `github-ae2f1d6bda86-38033862332`。
- 只清理荷小悦 `incoming` 中超过7天、对应已安装release存在且MANIFEST通过的27个重复压缩包及其校验文件，共298897532字节（约285MiB）。每个压缩包先核对SHA256，清单指纹 `6da61556f8a27cfd4cd375f43126c2605fd1e7850d04a22716e9f2070fef95bb`匹配才删除；一个旧release的MANIFEST不匹配，已跳过，未修复或删除。
- 已安装release目录、current、数据库备份、数据库卷、业务数据及其他项目均未删除；压缩包可由保留release重新打包恢复。清理后容量门禁通过：available_kb=3390060、required_kb=3145728。
- 原失败工作流已完成，原gateway不覆盖既有workspace；恢复采用同一主干SHA和成功CI的新正式工作流，不重跑原job、不关闭门禁、不重复未知状态dispatch。等待连接曾丢失，先只读等待原进程最终结果后再定向处理容量错误。

## 生产核验

- 恢复正式发布 [38041876765](https://github.com/zzzai/hxydiy/actions/runs/38041876765)成功，资格检查及“Backup, rehearse, deploy and verify”成功；安装current为 `github-b83174206afe-38041876765`，MANIFEST全量通过。
- 公网HTML引用安装版本，JS `/assets/index-gEbZhxkS.js` SHA256 `1771ef917246989d1970f7ceeced0dc97614daf150634f1dddfd2188ed8ee46e`，CSS `/assets/index-pzX0vB9a.css` SHA256 `0f2c8c719d9caef3aff514d86d76318aee8ed0cb7233394f54e715b316de04a7`，与服务器安装内容一致。
- 实际bundle包含新弹层、长按主提示、名称复制及自愿/授权说明，不再含“复制备用链接”；底部弹层和图片长按CSS生效。公网QR逐字节SHA256与原图一致，企微指令保留。
- 健康200、匿名本人报告/授权401、TCM内部读取公网404；没有生产业务写入或真实健康报告读取。原服务位页面显示“本次位置已释放”，未据此推定登录或执行重新占位。
- 生产IAB从不含服务位的固定回访URL进入，匿名个人页“查看入口”可打开新弹层；390×844实际原QR完整加载258px源图/218px显示、user-select:auto，关闭按钮有效。截图 `output/service-account-sheet-20261010/production-sheet-390.png`；未登录、未读报告、未关注服务号，临时手机视口已恢复且临时页关闭。该浏览器UI核验不替代微信真机识别/关注。
- 总控证据 `output/service-account-sheet-20261010/production-verification.json`、deployment.json（原容量失败）、deployment-recovery.json（恢复成功）。本次文档补录不再次部署。

## 现场边界

- 本地为合成顾客/服务位，无生产占位、选单、关注、消息推送或健康报告读取。
- 微信手机长按识别服务号、关注及底部菜单回访需要用户现场确认；本地渲染、离线解码、CI或服务器成功均不能替代现场验收。
- 门店回访链接仍为 `https://diy.hexiaoyue.com/?store=1&view=return`；到店选项目保留位置核对，不将关注服务号作为服务或本人报告访问条件。
