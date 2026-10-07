# TCM-ORIGINAL-REPORT-02 增量规格

- 状态：2026-10-07已统一发布，见 `../operations/tcm-original-report-release-20261007.md`；用户明确允许代确认新版授权后正式查询成功但当前手机号无报告，当前本人真实详情需对应号码的真实报告；微信/现场未验收。总控协调前端与发布，后台窗口唯一维护后端/来源/契约。
- 基线：`d24557e`；权威契约：`../contracts/tcm-my-reports-v1.md`。
- 目标：有效登录顾客重新单独同意外部完整报告范围后，取得经本人归属校验的原站链接；保留简版 fallback。
- 非目标：不写 diy-web，不做 iframe/媒体代理，不更正异常来源手机号/历史归属，不改 webhook 认证或导入顾客，不由本窗口安装/发布生产。
- 已确认：前次只读校准样例的来源 `report_print_url` 路由和编号匹配；不能据样例猜所有编号。前次 flow audit 证明来源实时读同一库，但停留页面不主动刷新。原站链接公开持有即可打开，DIY撤回不能令已获得链接失效。
- 规则：列表保持最小字段；详情新增 nullable `original_report_url`，仅从该条来源链接严格校验并重建。允许固定 HTTPS host/path/fragment route、唯一 `reportId` 且等于已校验本人 `report_no`；未知域、userinfo/port、额外查询/重复参数、编号错配、控制字符、反斜线均返回 null，不伪造缺失链接。DIY再次验证来源输出。原站不收到手机号/JWT/读取密钥。
- 新同意：`tcm-report-access-v2-original`；旧有效同意不满足新版读取，状态接口返回 false 和新版 notice/version，旧前端可提交返回版本。旧版本 POST 拒绝；有效登录与手机号证明不变，无新迁移。
- 验收：恶意/缺失来源链接、v1授权拒绝/v2授权成功、anonymous/staff/跨人拒绝、简版兼容、真实socket隔离 POST→整理→同登录新授权→正确本人链接，重复推送仍幂等；OpenAPI/types/合同/TEAM同PR。来源模块安装由总控按独立备份与精确SHA执行；原站 iframe/微信表现不当作本后端验证已完成。
