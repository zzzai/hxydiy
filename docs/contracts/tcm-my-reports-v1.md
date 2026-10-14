# TCM-MY-REPORTS-01：本人检测报告 v1

## 2026-10-14 P1 已发布报告中心

`CUSTOMER-EXPERIENCE-P1-20261014`已随#266与顾客实现、合同测试和共享记忆同批合并/发布，SHA`d9b4e520675c75910704ba93b3632e65b7dbbab2`。实际安装及未验范围见`../operations/customer-experience-p1-release-20261014.md`；下列差异不改变本人接口/权限，也不外推微信/provider现场通过。

- 首页、选座页、个人中心及显式旧`view=return`均承接统一专用报告任务；裸门店回访、菜单、二维码和分享语义不顺带改变。报告入口不要求选座、不创建/恢复占用或共享选单，门店参数不作为本人归属证明。
- 首次明确“登录并查看报告”或有效会话上的明确查看仍按既有v2动作链处理；有有效本人会话和有效v2记录可读取最新有效原报告。通用登录、页面加载、focus和恢复不补同意记录，不新增独立勾选或授权中转。
- 打开原站前保存报告中心返回状态；浏览器Back返回最近报告/历史/浏览门店项目/更多中心，不重新自动打开。再次查看与历史报告必须明确点击并重新校验详情；更多保留换号码及既有查看说明/撤回渠道，不移除权限校验。
- 最新日期不确定、无报告、最新链接缺失/非法、403、换号/退出和迟到响应显示真实状态或取消在途操作；不猜URL、报告归属或自动改开旧报告。菜单仍为无座位公开目录，不产生选单写入。
- 原站同页打开仍保留no-referrer和严格报告ID/地址匹配；不iframe、分享、媒体代理或新增总部/面部用途。合成浏览器场景不等于真实微信及原站验收。

既有发布基线与历史范围：本人简版、原站完整报告及报告专用入口的精确发布记录见`CURRENT-STATE.md`和相关operations记录。本文件规定接口边界，不作为当前安装证明；文件名保留以兼容已有引用。

`REPORT-ENTRY-SHORT-20261013`的原设计说明保留在下文，历史发布以专用发布记录为准；本批P1已发布差异见顶部。不改变以下本人接口、v2范围或现有权限。

## 身份与独立同意

- 仅当前有效顾客 JWT；员工、管理员、技师、匿名与被替换的会话不可读。不依赖会员资格，不接受调用者手机号或身份覆盖参数。
- 新短信登录与短信换机 JWT 签入 `phone_verification=sms-v1` 和当前手机号 SHA-256。签名、当前 `login_version`、当前手机号摘要必须同时匹配。
- 旧 JWT 缺此字段不等于要求重新验证：当前版本有效，且当前手机号成功 OTP 的 `used_at` 精确等于 `User.last_login_at`，发送/过期/尝试次数有效，即无感复用。任意历史验证码、仅数据库手机号、微信身份或可信设备 Cookie 不构成此证明。
- 普通登录不表示健康信息同意。独立使用 `CustomerProfileConsent` 的 `tcm_report_access`，版本升级为 `tcm-report-access-v2-original`，范围为当前手机号摘要、本人及原站完整报告入口；不新增健康数据表或迁移。旧 `tcm-report-access-v1` 不自动满足新范围，状态返回 false、新版 notice/version，报告读取403，必须本人明确新同意；旧版 POST 返回422。登录有效时无需重新OTP。
- 撤回只要求当前有效顾客身份，不要求重新证明手机号；号码变更后仍可撤回自己的记录。撤回后每次报告读取立即拒绝；已完成的响应不可能被远程收回。

## 顾客 API（均 `/api/v1` 前缀）

| 方法与路径 | 输入 | 输出 |
| --- | --- | --- |
| GET `/me/tcm-report-consent` | 无 | `consented, version, notice` |
| POST `/me/tcm-report-consent` | `accepted: true, version: tcm-report-access-v2-original`；禁止额外字段 | 同上，重复同意不重复创建有效记录 |
| DELETE `/me/tcm-report-consent` | 无 | 同上，`consented=false` |
| GET `/me/tcm-reports` | `limit=20`（1–20）、`offset=0`（0–100000） | `items, limit, offset, has_more` |
| GET `/me/tcm-reports/{report_id}` | ID 为 1–128 个字母数字、下划线或连字符；无查询参数 | 报告详情 |

列表条目仅 `report_id, reported_at, title=检测报告`。时间为含时区 ISO 8601 或 null。详情附加 `physiques[{name,score}]`（最多9项）、`heart_rate, blood_oxygen, moisture`，缺失为 null；不新增诊断、建议或评分解释。

详情新增 `original_report_url: string | null`。除这一严格校验的原站入口外，仍严禁输出姓名、手机号、图片、音频、其他供应商直链和原始载荷。不提供媒体代理。列表字段不变；所有路径禁止未知/重复查询参数（含客户端url），POST禁止额外字段。

## 原站完整报告入口与隐私边界

- 在服务端有效手机号登录、新版独立授权、`phone + report_no` 归属均通过后，从该条来源 `report_print_url` 校验取得链接。仅允许 `https://yk.qianmaitcm.com/print_smart_healthcare/#/discriminateRingReport?reportId=<本人已匹配编号>`。
- 固定 scheme/netloc/path/fragment route；禁止 userinfo/port、反斜线/控制字符、顶层query、额外或重复fragment参数；唯一 `reportId` 解码后必须精确等于该条 report_no，编号限ASCII字母数字/下划线/连字符1–128。通过后由固定常量和严格编码重建链接，不透传输入URL。TCM源与DIY输出schema分别校验。
- 缺失、非法或编号错配时返回 null，不根据report_id猜造链接；简版字段保留。旧源未给新字段时新DIY默认null；旧DIY忽略新源额外字段，可继续简版。新版授权升级仍须前端与DIY统一发布。
- 原站链接持有人无需原站登录即可打开，可能查看完整个人/健康信息。DIY只控制链接发放，不能阻止转发，撤回DIY授权不能使已获得链接失效；首次外部范围授权必须明确说明这些事实。原站自行处理其内容、追踪与链接有效性，iframe/微信表现未作为本后端已验收事实。
- 非报告专用页由顾客显式打开原站，不自动跳转；报告专用入口仅按下节的本人动作或有效既有记录直达。两类路径均不预加载原站、不做iframe或分享；保留 `noopener,noreferrer`/no-referrer，不向原站传手机号、JWT、读取凭据或DIY引用页参数。原站展示内容不由DIY新增诊断或复制媒体。

## 报告专用入口交互（2026-10-13基线；P1差异见顶部）

- 新 `view=reports` 是本人报告专用入口，不改变旧 `return/menu`、服务号入口或已打印QR语义；不选座、不创建/恢复选单、不消费旧服务位或选单凭据。`store` 参数不是报告归属证明。
- 普通页面进入、普通登录/验证码发送、登录成功回调本身均不代表同意。专用入口在短信表单展示现有v2本人范围和原站链接风险说明，由顾客明确提交“登录并查看报告”；号码验证成功后复用有效v2记录，必要时在该动作链中按现有POST记录 `accepted:true` 与既有v2版本，再同页进入严格校验的最新原站报告。没有勾选页、独立授权页或简版预览中转，不把通用登录改成自动授权。
- 已有有效本人号码会话且v2记录有效时，可从专用入口直接读取并打开最新原报告，不重复POST。记录缺失、旧版或已撤回时，仅在同页明确“查看本人报告”动作后按需POST，不在页面加载、恢复、focus或预取中补记录，不要求已验证会话再次发验证码。
- 列表API仅内部用于确定目标，不展示报告列表中转；最新检测时间无法确定、无报告或最新链接缺失/非法时显示真实状态，不猜URL、不自动改开更早报告。每次读取仍执行当前手机号证明、本人归属和v2有效性检查，跳转仍核对返回链接与报告ID严格一致。
- 首次外部范围告知保留：原站链接获得者可读、可能转发；DIY撤回不能失效已取得链接。已有同意复用不隐去这些风险，既有撤回渠道仍可发现。检测时授权不等于已写入DIY v2记录，本入口不扩展总部/照片/推送用途；退出、换号或失效后取消在途读取，迟到响应不能打开其他号码报告。

错误：401 未登录/失效/非顾客；403 `PHONE_VERIFICATION_REQUIRED` 缺当前号码证明或 `TCM_CONSENT_REQUIRED` 未单独同意；404 本人不存在/其他人报告统一；422 非法参数；503 `TCM_UNAVAILABLE` 未配置/上游不可用；502 `TCM_SOURCE_INVALID` 超时/非法/过大上游响应。错误不透传上游正文。API 使用既有 no-store 中间件。

## 独立 TCM 只读契约

- GET `/api/tcm/readonly/reports` 与 `/api/tcm/readonly/reports/{report_id}`；页参数同上，身份仅服务器专用 `X-TCM-Verified-Phone` 头，禁止 URL 手机号。
- Bearer 为独立读取密钥；传入已有 admin/webhook 密钥列表校验，重用时关闭。只接受实际 socket 对端 loopback 或 `172.18.0.0/16`，不信任 `X-Forwarded-For`；安装方必须禁止公网反向代理此命名空间。
- DIY 仅连接固定 `http://172.18.0.1:18090`，不跟随重定向、不使用环境代理、连接2秒/读取5秒、响应上限256KiB；无读取密钥默认关闭。
- SQLite `mode=ro` 与 `query_only`，参数化 phone+report_no 所有权查询，排除 `PROBE-%`；最大读取21条、结构化输入上限512KiB。数据库连接每次关闭；不修改报告/发送短信/导入顾客。
- 首批源模块已由总控安装；`TCM-ORIGINAL-REPORT-02` 只替换已审查的 `readonly_reports.py`，保留现有main挂接、独立密钥、webhook认证、数据库与迁移。固定旧源SHA校验、备份恢复后先装兼容源，再统一发布新版DIY/顾客端；安装与生产验证由总控协调。

安装边界与检查见 `../../tools/integrations/tcm/README.md`。
