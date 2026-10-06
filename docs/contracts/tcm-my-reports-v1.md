# TCM-MY-REPORTS-01：本人检测报告 v1

状态：开发契约，尚未合并、安装或发布。不得据此宣称生产可用。

## 身份与独立同意

- 仅当前有效顾客 JWT；员工、管理员、技师、匿名与被替换的会话不可读。不依赖会员资格，不接受调用者手机号或身份覆盖参数。
- 新短信登录与短信换机 JWT 签入 `phone_verification=sms-v1` 和当前手机号 SHA-256。签名、当前 `login_version`、当前手机号摘要必须同时匹配。
- 旧 JWT 缺此字段不等于要求重新验证：当前版本有效，且当前手机号成功 OTP 的 `used_at` 精确等于 `User.last_login_at`，发送/过期/尝试次数有效，即无感复用。任意历史验证码、仅数据库手机号、微信身份或可信设备 Cookie 不构成此证明。
- 普通登录不表示健康信息同意。独立使用 `CustomerProfileConsent` 的 `tcm_report_access`，版本 `tcm-report-access-v1`，范围为当前手机号摘要与本人；不新增健康数据表或迁移。
- 撤回只要求当前有效顾客身份，不要求重新证明手机号；号码变更后仍可撤回自己的记录。撤回后每次报告读取立即拒绝；已完成的响应不可能被远程收回。

## 顾客 API（均 `/api/v1` 前缀）

| 方法与路径 | 输入 | 输出 |
| --- | --- | --- |
| GET `/me/tcm-report-consent` | 无 | `consented, version, notice` |
| POST `/me/tcm-report-consent` | `accepted: true, version: tcm-report-access-v1`；禁止额外字段 | 同上，重复同意不重复创建有效记录 |
| DELETE `/me/tcm-report-consent` | 无 | 同上，`consented=false` |
| GET `/me/tcm-reports` | `limit=20`（1–20）、`offset=0`（0–100000） | `items, limit, offset, has_more` |
| GET `/me/tcm-reports/{report_id}` | ID 为 1–128 个字母数字、下划线或连字符；无查询参数 | 报告详情 |

列表条目仅 `report_id, reported_at, title=检测报告`。时间为含时区 ISO 8601 或 null。详情附加 `physiques[{name,score}]`（最多9项）、`heart_rate, blood_oxygen, moisture`，缺失为 null；不新增诊断、建议或评分解释。

严禁输出姓名、手机号、人脸/舌象图片、音频、供应商直链和原始载荷。不提供媒体代理。本轮前端不得期待照片字段。所有路径禁止未知/重复查询参数，POST 禁止额外字段。

错误：401 未登录/失效/非顾客；403 `PHONE_VERIFICATION_REQUIRED` 缺当前号码证明或 `TCM_CONSENT_REQUIRED` 未单独同意；404 本人不存在/其他人报告统一；422 非法参数；503 `TCM_UNAVAILABLE` 未配置/上游不可用；502 `TCM_SOURCE_INVALID` 超时/非法/过大上游响应。错误不透传上游正文。API 使用既有 no-store 中间件。

## 独立 TCM 只读契约

- GET `/api/tcm/readonly/reports` 与 `/api/tcm/readonly/reports/{report_id}`；页参数同上，身份仅服务器专用 `X-TCM-Verified-Phone` 头，禁止 URL 手机号。
- Bearer 为独立读取密钥；传入已有 admin/webhook 密钥列表校验，重用时关闭。只接受实际 socket 对端 loopback 或 `172.18.0.0/16`，不信任 `X-Forwarded-For`；安装方必须禁止公网反向代理此命名空间。
- DIY 仅连接固定 `http://172.18.0.1:18090`，不跟随重定向、不使用环境代理、连接2秒/读取5秒、响应上限256KiB；无读取密钥默认关闭。
- SQLite `mode=ro` 与 `query_only`，参数化 phone+report_no 所有权查询，排除 `PROBE-%`；最大读取21条、结构化输入上限512KiB。数据库连接每次关闭；不修改报告/发送短信/导入顾客。
- 2026-10-06 只读核验：实际 `tcm-webhook.service` 在 `/opt/tcm-ingest`，监听 `172.18.0.1:18090`，健康200。现有代码没有本契约只读路由；离线模块安装、独立密钥配置及生产验证由总控协调。

安装边界与检查见 `../../tools/integrations/tcm/README.md`。
