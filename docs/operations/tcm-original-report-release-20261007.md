# TCM-ORIGINAL-REPORT-02 生产交付

- 目标：DIY 菜单 → 我的 → 我的检测报告 → 本人详情 → 打开完整检测报告。已有有效手机号登录不重复验号；独立健康授权升级到 `tcm-report-access-v2-original`，旧授权不自动扩大。
- 后端 PR #209 HEAD `97db9278930de570a54bcab0af358dd9a83fdbe2`，合并 `49cb8096927495394ecaa0fd2475fc97bccb4144`，主干 CI `37565591362` 成功。顾客端 PR #210 HEAD `f90bd343b26565d43b35ecee7c00c88c3fb86d1f`，合并主干 `9b3344dac7d1e33e6a8510004703326e312c2d0d`，主干 CI `37566300784` 成功。
- 正式部署 `37566548934` 成功。服务器 `hxy` 的 current 为 `/root/hxy-diy-20260811/releases/github-9b3344dac7d1-37566548934`，MANIFEST校验通过；DIY/TCM健康200、匿名授权及报告401、来源公网读取404。未改菜单、评价、会员或报告归属，无数据库迁移。
- 来源只读模块精确 SHA256 从 `124b77bc47a9617bd62aba189174d8d0e43372c0bda2504edc9d139505eede4b` 升级为 `695bbd707add456fdbae90df1122e79069bceb7a6cb5e639bece5aa507713008`。安装脚本 SHA256 `69659c0c17160eaebfe74e6fd22166bae1ee5ff7ba0b6d9926fb8f83a01f22bd`；预检、SQLite一致备份及恢复副本完整性通过。备份 `/opt/tcm-ingest/data/reader-original-backup-20261007T031614Z-01f0752b979446dea91d7e504ff78dde`，仅原子替换reader并重启 `tcm-webhook`，健康通过。保留uid/gid/0640、main、既有密钥、webhook、代理和原报告数据；失败只回退reader，不回退数据库。
- 后端58项相关测试、9个登录子测试、最终20项API/client回归通过；Linux备份/回滚专项3项及真实Uvicorn TCP推送→同登录新版授权→本人链接通过。旧来源缺字段返回null；新来源兼容实际旧schema；恶意、缺失和编号错配链接不生成，跨人404，重复推送仍幂等。
- 顾客端构建与既有19项测试通过；375/390 × 两个独立账号及空态共6组真实隔离FastAPI/SQLite联调通过。只外部来源为合成数据，原站请求拦截为合成HTML：明确授权升级、链接归属、用户点击才打开且无Referer/opener、刷新失败保留列表、focus/visibility去重、无链接fallback、401/403、撤回/换号/退出迟到响应丢弃。无健康数据本地存储/埋点、无短信或选单写入。证据在顾客工作区 `diy-web/output/playwright/tcm-original-report-02/result.json` 及同目录截图；总控审查回执，不重复运行。
- 生产仅核查用户已提供的原站样例，来源本人详情200、跨人404，链接与该条来源匹配；实际DIY容器的正式source client同样通过链接校验与跨人拒绝。未输出手机号、健康结果或密钥，没有伪造顾客登录/授权。服务器证据 `/root/hxy-diy-20260811/operations/tcm-original-production-20261007-9b3344dac7d1.json` 与 `tcm-original-reader-install-20261007.json`；桌面发布报告 `C:/Users/gaoji/AppData/Local/Temp/TCM-ORIGINAL-RELEASE-20261007.json`。
- 生产本人内置浏览器实测：菜单进入我的，再进入报告页；登录保留、无重复验号，新版授权说明和未勾选状态可见。用户在本轮明确允许代确认这次新版授权后才勾选提交，正式报告查询成功，当前登录手机号仍为空列表，刷新入口和到店检测提示可见。没有换成他人手机号，不把来源样例可读当作当前本人已有报告。当前本人真实详情受阻于该账号无匹配报告；需本人使用检测时号码登录或接收该号码的新检测，不能自行重绑来源。微信真机和门店现场未验收。
- 原站页面是链接持有者可访问；授权说明公开这个边界。DIY撤回会停止DIY查看，但不能令已获得或转发的原站链接失效；不将样例URL绑定全部顾客，不用iframe或自动跳转，也不虚构原站访问控制。

本次仅记录已发布事实，文档提交不重复部署。
