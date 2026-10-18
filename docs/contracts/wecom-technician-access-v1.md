# 企业微信技师身份与在店顾客档案 v1

状态：v1 已通过 #278 合并并发布 `05a837d1c7e45145b71243709a1e3ad996006162`；具体备份、迁移与公网验证见 `../CURRENT-STATE.md`、`../WORK-STATUS.md`。2026-10-18 总控独立完成专用测试身份的真实 Windows 企微工作台静默首登及空服务列表；真实报告来源、手机、真实 BFCache 命中和现场验收仍未完成。下文原隔离失败保留为历史，不表示当前仍暂停。后续单门店店长增量见 `wecom-store-staff-v2.md`，其开发和发布状态单独记录。

## 范围与存储

仅新增 `StaffExternalIdentity`、`StaffOAuthAttempt`、`CustomerTagContribution` 三表。迁移文件 `20261017_wecom_technician.py`，不回填、合并或清理旧顾客/标签数据。密码登录、价格、无座流程、v7 服务记录、原门店待认领入口不改变。不新增 Redis、服务前授权表、外部标签同步或派单系统。

外部员工身份以 provider/corp_id/规范化 userid 唯一匹配明确绑定的 Staff，不通过手机号或姓名猜测。只有在职、同店、绑定当前技师且技师状态 available/busy 的账号可用。企业微信应用关闭、成员禁用/离职、身份不匹配或不在应用可见范围，均拒绝。

可见范围由该自建应用 Secret 获取的同一 access_token 调用官方 `user/get` 校验，允许企业微信正常部门授权；不要求 `agent/get.allow_userinfos` 逐人列出成员，不自行复制部门树，也不回退到通讯录同步或其他应用 token。仍检查 `agent/get` 返回的 AgentID 和 close=0。官方依据：[读取成员](https://developer.work.weixin.qq.com/document/path/90196)，2026-10-18 核对页面标注更新于 2025-03-06，说明应用只能读取可见范围内成员。官方拒绝、超时、身份不符或非在职均拒绝新登录及到期证明刷新，失败不续期；权限撤回最多沿用既有 300 秒证明窗口，不承诺即时同步。

受控绑定工具 `python -m scripts.bind_wecom_identity --input /private/input.json` 默认只读预览，应用需 `--apply --expect-preview-sha256 <sha>`。输入权限仅属主可读写，不含 Secret；必须显式 CorpID/UserID、门店及现有 Staff/Technician，或明确批准的专用测试账号字段。官方在线复核、锁后重算预览、数据库唯一约束、单事务、审计和重复零写保护；冲突不覆盖、不自动重绑、不恢复禁用身份。测试新建仅增加一名 Staff、一名 Technician 和一条绑定及其审计，不改旧管理员、旧测试员工、顾客、余额或订单；随机密码只哈希保存，不交付明文、不发短信。测试技师会出现在本店列表，可被管理员手动选择，不宣称隐藏或权限沙箱；本轮只验首登和空服务列表，不造单或派单。

## 登录与会话

- 显式工作台入口 `/technician/wecom` 每次先清旧身份、敏感页面状态及待提交数据，再重新验证当前企业微信身份。普通站内跳转不循环 OAuth，密码入口保留。
- `POST /api/v1/auth/wecom/authorize`：`{entry_nonce}` → `{attempt_id,authorization_url,expires_in}`。
- `GET /api/v1/auth/wecom/callback`：消费官方一次性 code/state，浏览器绑定验证后固定 303 到 `/technician/wecom/complete`；尾斜杠同处理，不通过框架 307 反射查询串。
- `POST /api/v1/auth/wecom/exchange`：`{attempt_id,entry_nonce}` → `{token,staff,auth_method:"wecom"}`，一次性消费。
- attempt TTL 300 秒，state/nonce/browser proof 仅存摘要。每次尝试使用独立 HttpOnly cookie；不使用可被旧响应覆盖或删除的共享 current cookie 判断先后。前端当前 pending attempt + epoch 防旧 authorize/exchange 成功回写；服务端独立校验该尝试的浏览器绑定、nonce、有效期及一次性消费，不声称单靠 cookie 实现服务端尝试取代。
- Axios 请求同步捕获会话 epoch/token；旧 200、旧 401 均转为 stale 错误，不渲染、清除、跳转或提示新会话。密码/激活成功同样按捕获 epoch 提交；退出和 BFCache 返回明确使旧身份失效。
- 每次员工请求检查本地账号、绑定及版本。企业微信证明超过 300 秒重新验证，失败关闭。解绑/重绑版本由数据库 UPDATE 原子递增；恢复绑定不复活旧 JWT，不因解绑修改密码凭证版本。受控 ORM 绑定写保证该规则；绕过 ORM 的直接数据库维护必须在同一 UPDATE 显式版本加一并清证明，普通应用不提供绕过写接口。
- 默认企业微信功能关闭。没有生产可调用的 synthetic 登录路由；合成 provider 只在测试依赖替换中存在。

OAuth 查询值不可进入浏览器后续 URL、审计、代理日志或遥测；官方固定 HTTPS 服务端 API 必须使用的 token/secret 查询参数仅限受控请求，不记录原始异常 URL。应用 callback 访问日志去查询；将来部署前仍必须核验反向代理/APM 同样去查询，目前未改生产代理。

## 本人任务与档案范围

新 `GET /api/v1/technician/my-tasks` 只返回当前技师本店本人 `in_service/post_service_present` 的在店占用，硬上限 100 条，项目白名单投影。原 `/technician/tasks` 保留门店待认领/区位列表语义，不冒充本人任务。

下列入口均为 `/api/v1/technician/occupancies/{id}/customer-*`，每次请求重新验证：本人服务、本店、有效原选单、占用仍活跃、未 departed/released。换人、跨店、离店、释放或清洁后拒绝完整档案，不依赖前端隐藏。历史记录仍按原本人服务历史权限读取。匿名选单继续可服务；summary 返回 unbound，明细返回 409 `CUSTOMER_UNBOUND`，不创建或猜测顾客。

| 入口 | 白名单结果 |
| --- | --- |
| summary | 当前顾客名称、会员等级，不展示余额 |
| history | 可靠绑定顾客的本店历史服务，日期与项目，不包含其他技师私密记录 |
| reviews | 可靠归属的真实服务评价和到店反馈 |
| reports / reports/{report_id} | 专用员工用途授权与来源校验后的规范化摘要/段落，默认不可用 |
| tags | 旧关系及有效贡献去重后的标签、来源和可选普通运营标签 |

分页使用 `{items,total,page,page_size}`；页大小默认20、最大100。请求不接受 customer/phone 身份覆盖参数。

评价不新增人工 approved 审核语义，也不把 follow_up_status 当批准。ServiceFeedback 与原 SelectionSession 的顾客/门店须一致且服务已完成；VisitFeedback 只采用真实绑定顾客/门店、标记“到店反馈”，没有服务外键时项目为空，不按座位或时间猜归属。评价附 `feedback_type:service|visit`、source、tags、projects；service source 为 completed_service，visit 保留真实来源。UI 使用 feedback_type+id 组合键。仅展示顾客反馈文字/分值/日期/项目，排除全部内部 follow_up 字段及身份/幂等摘要。

报告不代理 `/me/tcm-reports`，不签发顾客 JWT，不重弹顾客 H5 授权。真实来源与员工服务用途证据尚未接入，默认 `REPORT_ACCESS_UNAVAILABLE`；测试的明确合成正负授权只证明隔离行为，不代表真实来源已通。无脸部原图、公开持久原报告链接或营销用途。

## 普通运营标签

`GET customer-tags` 返回去重标签、每个旧/贡献来源及可操作性。技师只新增本次可靠服务上下文中的普通 manual 标签贡献；不得将 v7 服务画像转为运营标签。

`POST customer-tags {tag_id,idempotency_key}` 返回 `{id,tag_id,version}`。作者+门店+幂等键唯一，异载荷409；同作者同服务上下文仅一个有效贡献。撤回 `DELETE customer-tags/contributions/{id}` 携带 `{expected_version,reason}`，只能撤回本人贡献，不删除其他作者/旧来源；撤回后使用新幂等键可重新贡献。

保留店长原有合法同店旧 CustomerTagRelation 添加/删除接口，绝不因本批改为旧源只读。移除旧来源而仍有贡献时，标签继续显示剩余来源。字典已有任意贡献历史时 DELETE 返回409并提示停用，防止外键500或历史丢失；无贡献保留原行为。用户展示、筛选、分群、计数统一去重旧关系和有效贡献，不通过联表重复行放大分页。旧重复行不自动清理。

## 验收与发布边界

本地 SQLite/TypeScript 验证不能代替 PostgreSQL 条件唯一约束、锁等待及真实并发；合成报告不等于真实报告接入；任何检查通过均不等于现场或生产通过。

历史风险记录：隔离服务器曾在多窗口验证中出现 SSH/banner 及公网连接不可用，原因当时未核实；本批 PG/test 初建无资源上限，当时暂停新增远程任务。随后已恢复，验证改为串行且受限：测试容器512MiB、PG256MiB、各0.5CPU，保留3GiB磁盘门槛。原失败不得抹去，不能因此自动重试无上限构建或清理生产数据。
