# TCM-MY-REPORTS-01 增量规格与执行计划

状态：开发中，未安装/配置/发布生产。总控负责发布，管理后台窗口为后端及离线TCM模块唯一写入方。基线87f0ad4；菜单分支完全独立。

## 目标与边界

DIY顾客无感复用当前已验证手机号会话，单独同意后只读本人报告。撤回即停止访问。无会员门槛，无导入、短信/企微推送、诊断生成、照片代理或第三方报告直链。接口不接受caller phone，不把User.phone/任意历史验证码/设备cookie单独视为证明，不改生产数据/配置。

## 已核事实

2026-10-06 tcm-webhook active、内网health200；源码无wecom_delivery或by-phone接口，内网by-phone404。现有recent接口需admin凭证，禁止复用。tcm-check因incomplete告警返回1，不是webhook宕机。仅复制main/db/config/quality/migrations源码到私有隔离目录，不含env/数据库/报告。字段模式已只读核对，来源不能识别门店，不构造store归属。

H5 OTP成功后used_at与User.last_login_at为同一个now，并推进登录版本；User.phone有非空唯一索引。旧会话可在手机号/成功使用时间/当前登录时间/版本全部匹配时复用；不匹配的旧微信/失效/改号会话才补验证。以后OTP令牌增加签名手机号证明以避免依赖验证码保留期限。设备绑定本身不保证短信验证，不能孤立授权。健康报告同意使用独立consent_type和版本，不因普通登录默认授权。

## 计划与完成标准

1. `tools/integrations/tcm/readonly_reports.py`：独立read token（拒绝admin/webhook）、仅内网地址、不信XFF、SQLite mode=ro、手机号参数化查询/索引、PROBE排除、分页/归属、最小列表和受限详情。离线SQLite+真实HTTP验证无凭证/公网/越权/注入/未知ID/照片链接不泄露。
2. `hxy-server/app/api/tcm_reports.py`及schemas/service：当前customer会话证明、独立同意/撤回（既有同意表）、列表/详情、固定内网上游与超时/不重定向/受限响应。真实HTTP覆盖旧已验证JWT无感复用、未验证/tech/staff/伪造phone/跨人ID/未同意/撤回/上游失败；不查询报告前就泄露检测存在性。
3. 更新auth签发证明、配置（默认关闭）、注册路由、OpenAPI/生成类型、合同/TEAM-MEMORY/安装说明。复用独立工作区与脚本等CI，不自动合并/发布。
4. 运行相关auth/隐私/TCM行为与合同测试、服务器断网隔离验证；前端字段冻结后交总控安排顾客窗口接入。总控审核源码与最小配置、安装索引（若缺失）/内网授权及生产发布；真机验收交人。

## 跨端契约

DIY路由归入/api/v1/me/tcm-reports及/me/tcm-report-consent；分页limit1..20、offset0..100000；列表仅report_id/reported_at/title和has_more，详情仅原始体质得分/心率血氧湿气等白名单，不返回raw payload、姓名手机号、面舌照/录音/直链。上游/api/tcm/readonly/reports及/{report_id}只接收DIY服务端已验证手机号，独立凭证绝不下发前端。具体类型在实现后以OpenAPI及合同冻结。

## 未决与依赖

生产只读凭证生成、TCM模块安装和访问控制由总控协调，未配置时fail closed，不以管理员recent接口兜底。现有监控incomplete告警单独处理，本任务不改或清理报告。
