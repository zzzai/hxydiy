# 企业微信门店员工接入 v2 增量

状态：2026-10-18 已批准设计、实现中；基于 #278 的主干 `05a837d1c7e45145b71243709a1e3ad996006162`，不表示本增量已发布。

## 范围与角色

仅支持明确本店的在职技师与店长；不支持总部、普通员工、未知角色或多工作区。企微 canonical UserID 必须经同一应用官方接口确认，登录不能按姓名或手机号猜绑定。正式建号输入只在仓库外的受限私有文件，个人数据不写本契约。

- 技师：原 `Staff.role=technician`、同店 Technician、available/busy 和身份版本规则保持。
- 店长：数据库 `Staff.role=manager`；Staff 与外部身份的 `technician_id` 必须均为 null；`store_id` 指向同一真实门店。必须恰好一条 active `StaffScopeAssignment`，且 role=`store_manager`、scope_type=`store`、scope_id=绑定门店。
- 缺授权、多授权、总部授权、其他门店、普通员工或角色错配均拒绝，不挑选第一项，也不借 legacy token 默选。

## OAuth 响应与每次请求

沿用 v1 authorize/callback/exchange、一次性浏览器绑定、epoch、防重放及300秒官方证明。技师响应不变。

店长 exchange 返回：

```json
{
  "token": "<server-signed scoped token>",
  "auth_method": "wecom",
  "staff": {"id": 1, "name": "<name>", "role": "store_manager", "store_id": 1, "technician_id": null, "store_name": "<store>"},
  "selector_token": null,
  "workspaces": [{"assignment_id": 1, "role": "store_manager", "scope_type": "store", "scope_id": 1, "scope_name": "<store>"}]
}
```

示例编号为说明而非真实身份。JWT 使用既有 `token_type=staff_scope`、真实 `role=store_manager`、精确 assignment_id/scope_type/scope_id，同时保留 WeCom external_identity_id/binding_version/credentials_version。每次请求重验 Staff、身份和唯一授权；授权撤销、角色/门店改变、JWT scope 不符立即拒绝，不受官方证明缓存窗口影响。

前端严格校验 staff 正整数 id/store_id、technician_id=null、selector_token=null 和唯一同店 grant，再复用现有导航别名 manager，固定进入 `/admin/#/today`。技师壳的 pagehide 清理仅针对真正技师，不清掉正在交给管理后台的店长会话。总部、任意 return URL 和多工作区选择均不在本批范围。

原技师任务/报告/标签接口仍只接受技师且维持本人当前在店服务范围；店长只获得其既有门店管理权限，不借此取得技师顾客档案新权限。

## 数据与运维

新增迁移仅放宽外部身份 technician_id 的非空约束，保留 FK、唯一约束和所有旧绑定。降级若存在空技师编号身份必须拒绝，不能通过删除绑定满足非空约束；应用回滚保留数据。

正式员工批次工具与 `create_test` 分开：默认预览、明确每人的 canonical subject/门店/真实角色/账号资料、精确预览摘要确认、锁后重查、同名或手机号/账号/企微主体冲突拒绝、整批事务、审计、重放零新增。店长只建 Staff、唯一门店授权与绑定；技师只建 Staff/Technician/绑定；随机密码只在内存生成并哈希，不发送明文或短信，不修改旧账号和授权。

本批仅用户明确批准的三人；其他员工、顾客、订单、余额、会员资料不变。复用服务器 Secret，真实备份恢复/定向回归/必需 CI 后才迁移与应用，不把脚本预览视为完成。

正式工具：`python -m scripts.provision_wecom_staff --input /private/batch.json`。应用追加 `--apply --expect-preview-sha256 <完整摘要>`。顶层为 `corp_id/store_id/members`；最多三名成员，每人明确 `label/userid/username/name/role`，label 仅用 `manager_1` 或 `technician_1` 等非个人编号；技师另需 `phone/code`，店长禁止技师字段。仅复用本工具同一完整请求审计确认的整批结果；部分已存在、旧身份停用、角色改变或资料冲突均拒绝，不自动修复旧人。手机号来自已批准私有清单；官方未返回手机号时不宣称已官方核验手机号。

既有单人绑定 CLI 支持明确 `technician_id:null` 的合法单店店长，仍需完整 Staff/门店指定和唯一授权；不经 `create_test` 路径创建正式员工。随机密码不可知，仅哈希保存；后续任何重设须走原有受控流程。
