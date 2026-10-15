# TCM-MY-REPORTS-01：本人检测报告 v1

## 2026-10-15 CUSTOMER-REPORT-NO-EXTRA-CONSENT-20261015（已生产，现场待验）

用户确认检测时已经完成授权，顾客本人后续查看报告不需要再次授权。本人报告列表和详情不再查询或要求 DIY `CustomerProfileConsent` v2/active 记录，也不新增原检测授权证明门禁；无记录、旧 v1、已撤回或有效 v2 均按同一本人身份规则读取。以下当前接口与交互条款取代历史发布中的独立 v2 门禁说明。#272已合并/发布`0b88c66e57639fe70ef8e5f09a10f6ddf48a5d72`，独立来源reader同步升级；实际安装及微信/真实原站未验范围见`../operations/customer-report-no-extra-consent-release-20261015.md`，本文不是独立生产证明。

仍校验有效顾客 JWT、当前登录版本、当前手机号短信证明及来源 `phone + report_no` 归属；这属于本人身份校验，不等同新增授权。读取不创建、升级、补写或删除授权/审计记录，普通登录不写为 consent。历史授权接口保留兼容，其状态和撤回不再决定本人报告读取权限。本次不扩大到他人、员工、总部、下载、营销或面部图用途；这些用途的个人数据规则不因本变更被忽略。

## 2026-10-14 P1 已发布报告中心

`CUSTOMER-EXPERIENCE-P1-20261014`已随#266与顾客实现、合同测试和共享记忆同批合并/发布，SHA`d9b4e520675c75910704ba93b3632e65b7dbbab2`。实际安装及未验范围见`../operations/customer-experience-p1-release-20261014.md`；下列差异不改变本人接口/权限，也不外推微信/provider现场通过。

- 首页、选座页、个人中心及显式旧`view=return`均承接统一专用报告任务；裸门店回访、菜单、二维码和分享语义不顺带改变。报告入口不要求选座、不创建/恢复占用或共享选单，门店参数不作为本人归属证明。
- 历史 P1 首次“登录并查看报告”和有效会话查看采用 v2 动作链；本次修正改为完成本人身份校验后读取，不再要求或补写 v2 记录，不新增独立勾选或授权中转。
- 打开原站前保存报告中心返回状态；浏览器Back返回最近报告/历史/浏览门店项目/更多中心，不重新自动打开。再次查看与历史报告必须明确点击并重新校验详情；更多保留换号码，不新增查看说明或授权操作。
- 最新日期不确定、无报告、最新链接缺失/非法、403、换号/退出和迟到响应显示真实状态或取消在途操作；不猜URL、报告归属或自动改开旧报告。菜单仍为无座位公开目录，不产生选单写入。
- 原站同页打开仍保留no-referrer和严格报告ID/地址匹配；不iframe、分享、媒体代理或新增总部/面部用途。合成浏览器场景不等于真实微信及原站验收。

既有发布基线与历史范围：本人简版、原站完整报告及报告专用入口的精确发布记录见`CURRENT-STATE.md`和相关operations记录。本文件规定接口边界，不作为当前安装证明；文件名保留以兼容已有引用。

`REPORT-ENTRY-SHORT-20261013`的历史发布以专用发布记录为准；下列为当前已发布契约，不外推真实微信、原站或营业现场验收。

## 身份校验与兼容授权记录

- 仅当前有效顾客 JWT；员工、管理员、技师、匿名与被替换的会话不可读。不依赖会员资格，不接受调用者手机号或身份覆盖参数。
- 新短信登录与短信换机 JWT 签入 `phone_verification=sms-v1` 和当前手机号 SHA-256。签名、当前 `login_version`、当前手机号摘要必须同时匹配。
- 旧 JWT 缺此字段不等于要求重新验证：当前版本有效，且当前手机号成功 OTP 的 `used_at` 精确等于 `User.last_login_at`，发送/过期/尝试次数有效，即无感复用。任意历史验证码、仅数据库手机号、微信身份或可信设备 Cookie 不构成此证明。
- 本人列表和详情不执行独立 DIY 授权门禁，不要求来源授权证明，也不把登录或报告读取写成 consent。无需为查看报告创建或升级 `tcm_report_access` 记录，已有记录与审计保持原样；不新增健康数据表、迁移或配置开关。
- 兼容 `tcm-report-consent` GET/POST/DELETE：GET 仍仅反映既有 `tcm-report-access-v2-original` 记录状态，旧 v1 不自动升级，旧版 POST 返回422；仅显式旧接口 POST/DELETE 执行其原记录/审计行为。GET 返回 false 不表示报告不可读。
- 兼容撤回只要求当前有效顾客身份，不要求重新证明手机号；号码变更后仍可撤回自己的记录。撤回只更改该旧记录，不再阻断本人报告读取，也不能使已获得原站链接失效。

## 顾客 API（均 `/api/v1` 前缀）

| 方法与路径 | 输入 | 输出 |
| --- | --- | --- |
| GET `/me/tcm-report-consent`（兼容） | 无 | `consented, version, notice`；不决定报告读取权限 |
| POST `/me/tcm-report-consent`（兼容） | `accepted: true, version: tcm-report-access-v2-original`；禁止额外字段 | 同上，重复同意不重复创建有效记录；报告流程不调用 |
| DELETE `/me/tcm-report-consent`（兼容） | 无 | 同上，`consented=false`；不阻断本人报告读取 |
| GET `/me/tcm-reports` | `limit=20`（1–20）、`offset=0`（0–100000） | `items, limit, offset, has_more` |
| GET `/me/tcm-reports/{report_id}` | ID 严格为 ASCII `[A-Za-z0-9_-]{1,128}`；无查询参数 | 报告详情 |

列表条目仅 `report_id, reported_at, title=检测报告`。时间为含时区 ISO 8601 或 null。详情附加 `physiques[{name,score}]`（最多9项）、`heart_rate, blood_oxygen, moisture`，缺失为 null；不新增诊断、建议或评分解释。

详情新增 `original_report_url: string | null`。除这一严格校验的原站入口外，仍严禁输出姓名、手机号、图片、音频、其他供应商直链和原始载荷。不提供媒体代理。列表字段不变；所有路径禁止未知/重复查询参数（含客户端url），POST禁止额外字段。

## 原站完整报告入口与隐私边界

- 在服务端有效顾客身份、当前手机号短信证明及 `phone + report_no` 归属均通过后，从该条来源 `report_print_url` 校验取得链接。仅允许 `https://yk.qianmaitcm.com/print_smart_healthcare/#/discriminateRingReport?reportId=<本人已匹配编号>`。
- 固定 scheme/netloc/path/fragment route；禁止 userinfo/port、反斜线/控制字符、顶层query、额外或重复fragment参数；唯一 `reportId` 解码后必须精确等于该条 report_no，编号限ASCII字母数字/下划线/连字符1–128。通过后由固定常量和严格编码重建链接，不透传输入URL。TCM源与DIY输出schema分别校验。
- 缺失、非法或编号错配时返回 null，不根据report_id猜造链接；简版字段保留。旧源未给新字段时新DIY默认null；旧DIY忽略新源额外字段，可继续简版。API route、DIY 输出 schema 与只读源详情路由均拒绝非 ASCII 报告编号。
- 原站链接持有人无需原站登录即可打开，可能查看完整个人/健康信息。DIY只控制链接发放，不能阻止转发，也不能使已获得链接失效；这些固有事实记录于本合同，不要求前台另设查看说明或新增授权动作。原站自行处理其内容、追踪与链接有效性，iframe/微信表现未作为本后端已验收事实。
- 非报告专用页由顾客显式打开原站，不自动跳转；报告专用入口仅按下节的本人动作或有效本人会话直达。两类路径均不预加载原站、不做iframe或分享；保留 `noopener,noreferrer`/no-referrer，不向原站传手机号、JWT、读取凭据或DIY引用页参数。原站展示内容不由DIY新增诊断或复制媒体。

## 报告专用入口交互

- 新 `view=reports` 是本人报告专用入口，不改变旧 `return/menu`、服务号入口或已打印QR语义；不选座、不创建/恢复选单、不消费旧服务位或选单凭据。`store` 参数不是报告归属证明。
- 专用入口复用已有短信登录；无有效本人手机号会话时完成“登录并查看报告”，号码验证成功后直接读取严格校验的最新原站报告。不读取或写入 `tcm-report-consent`，不加勾选页、独立授权页、原检测授权证明或简版预览中转；普通登录不写成授权。
- 已有有效本人手机号会话时可从专用入口直接读取并打开最新原报告，不因 DIY 授权记录缺失、旧版或已撤回重新授权，也不要求有效会话再次发验证码。Back 返回报告中心不自动重开，再次查看与历史报告仍明确点击并重新校验详情。
- 列表API用于确定目标及中心历史，不展示最新报告的列表中转；最新检测时间无法确定、无报告或最新链接缺失/非法时显示真实状态，不猜URL、不自动改开更早报告。每次读取仍执行当前手机号证明和本人归属检查，跳转仍核对返回链接与报告ID严格一致。
- 前台不设置独立查看说明或额外授权门禁，原站链接访问与转发的固有边界见上节合同。本入口不扩展总部/照片/推送用途；退出、换号或失效后取消在途读取，迟到响应不能打开其他号码报告。

错误：401 未登录/失效/非顾客；403 `PHONE_VERIFICATION_REQUIRED` 缺当前号码证明；404 本人不存在/其他人报告统一；422 非法参数（含 Unicode 报告编号）；503 `TCM_UNAVAILABLE` 未配置/上游不可用；502 `TCM_SOURCE_INVALID` 超时/非法/过大上游响应。本人报告读取不再返回 `TCM_CONSENT_REQUIRED`。错误不透传上游正文。API 使用既有 no-store 中间件。

## 独立 TCM 只读契约

- GET `/api/tcm/readonly/reports` 与 `/api/tcm/readonly/reports/{report_id}`；页参数同上，身份仅服务器专用 `X-TCM-Verified-Phone` 头，禁止 URL 手机号。
- Bearer 为独立读取密钥；传入已有 admin/webhook 密钥列表校验，重用时关闭。只接受实际 socket 对端 loopback 或 `172.18.0.0/16`，不信任 `X-Forwarded-For`；安装方必须禁止公网反向代理此命名空间。
- DIY 仅连接固定 `http://172.18.0.1:18090`，不跟随重定向、不使用环境代理、连接2秒/读取5秒、响应上限256KiB；无读取密钥默认关闭。
- SQLite `mode=ro` 与 `query_only`，参数化 phone+report_no 所有权查询，排除 `PROBE-%`；最大读取21条、结构化输入上限512KiB。数据库连接每次关闭；不修改报告/发送短信/导入顾客。
- 首批源模块已由总控安装；`TCM-ORIGINAL-REPORT-02` 只替换已审查的 `readonly_reports.py`，保留现有main挂接、独立密钥、webhook认证、数据库与迁移。固定旧源SHA校验、备份恢复后先装兼容源，再统一发布新版DIY/顾客端；安装与生产验证由总控协调。

安装边界与检查见 `../../tools/integrations/tcm/README.md`。
