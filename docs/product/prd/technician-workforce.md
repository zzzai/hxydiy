# BR-06 技师档案、排班、请假与账号 PRD

关联：[README](README.md)、[technician-portal-production-prd.md](../technician-portal-production-prd.md)
优先级：P1
当前实现：账号生命周期和请假审批较强；档案/排班/在岗看板仍有缺口

## 1. 执行摘要

技师不是“员工账号”的附属字段。门店需要管理技师的可服务状态、班次、请假、服务能力；总部需要跨店查看人力配置。店长也是技师，因此这套能力同时服务店长端。

## 2. 问题与目标

- 技师档案信息分散，缺少擅长项目/资质/可服务门店；
- 没有排班，无法判断“现在谁在岗”；
- 请假只有记录，没有审批和影响处理；
- 停用账号后历史服务仍要保留；
- 店长绑定技师流程缺少异常处理。

目标：

1. 一个技师三条轴清晰：任职、在岗、账号；
2. 排班可被门店查看和调整；
3. 请假影响可自动提示冲突；
4. 档案变更可审计、可追溯。

## 3. 角色与范围

| 角色 | 档案 | 排班 | 请假 | 账号 |
|---|---|---|---|---|
| 总部管理员 | 全品牌 | 查看/模板 | 审批策略 | 创建/停用 |
| 店长 | 本店 | 本店维护 | 审批本店 | 邀请/停用本店（需授权） |
| 技师 | 本人 | 查看 | 申请/撤回 | 修改密码/设备 |
| 店员 | 本店只读 | 查看 | 无 | 无 |

## 4. 业务对象

### Technician

```text
id, staff_id, name, phone_masked, gender, avatar,
employment_status: active / leave / resigned,
work_state: available / busy / off,
skills: [{project_id, level}],
certifications[], joined_at, left_at,
primary_store_id, service_store_ids[]
```

### Shift

```text
id, store_id, technician_id, date,
start_at, end_at, break_minutes,
status: planned / confirmed / swapped / cancelled,
created_by, updated_by
```

### LeaveRequest

```text
id, technician_id, store_id, type: personal / sick / annual / other,
start_at, end_at, reason, status: pending / approved / rejected / cancelled,
approver_id, approved_at, impact_note
```

### AccountBinding

```text
staff_id, technician_id, credentials_version,
status, invited_at, activated_at, disabled_at
```

## 5. 状态机

### 任职

```text
active → leave → active
active/leave → resigned
```

### 在岗

```text
off → available → busy → available
```

规则：

- `work_state` 由服务/打卡/排班驱动，不由手工随意切换；
- 请假期间不可被安排新服务；
- 离职后账号立即禁用，历史保留；
- 店长必须绑定 technician_id 才能进入店长端。

### 请假

```text
pending → approved / rejected
pending → cancelled
approved → cancelled（开始前且无冲突）
```

## 6. 核心流程

### 6.1 新增技师

1. 总部/店长创建技师；
2. 填写档案、门店、擅长项目；
3. 创建员工账号并邀请；
4. 技师激活账号；
5. 绑定店长/员工角色；
6. 进入排班。

### 6.2 排班

1. 店长选择周/月；
2. 设置班次、休息、门店；
3. 系统校验同一技师时间冲突；
4. 发布排班；
5. 技师端查看。

### 6.3 请假

1. 技师提交时间、类型、原因；
2. 系统检查已有排班/服务；
3. 店长审批；
4. 通过后自动标记冲突排班；
5. 通知相关人。

## 7. 硬规则

- 技师档案与员工账号一对一；
- 店长必须有 technician_id；
- 离职/停用立即提升 credentials_version；
- 同一技师同一时间只能有一个班次/服务；
- 请假时间必须合法，跨天需明确；
- 审批人不能审批自己的请假；
- 排班变更影响已确认服务时，必须提示并处理；
- 所有敏感字段脱敏展示。

## 8. 权限与审计

- 店长只能维护本店技师和排班；
- 总部可跨店查看，不可无理由修改门店排班；
- 档案、排班、请假、账号状态变更全部审计；
- 离职/停用需要复核人。

## 9. 指标

- 在岗率、排班覆盖率；
- 服务冲突数；
- 请假审批时长；
- 技师服务量/评价均分；
- 店长绑定完整率；
- 账号激活率。

## 10. 验收标准

- [ ] 技师三条状态轴互不覆盖；
- [ ] 店长绑定技师且权限可验证；
- [ ] 离职立即失效令牌；
- [ ] 排班冲突可检测；
- [ ] 请假审批与排班冲突联动；
- [ ] 店长只能看本店；
- [ ] 历史服务/评价不因离职丢失。

## 11. 当前实现差距

- 员工账号/技师账号基础已有；
- 店长绑定技师流程有，但异常/解绑规则不完整；
- 技师档案字段与擅长项目未形成能力模型；
- 已实现技师管理页的请假审批：批准/驳回、驳回原因必填、审批审计、自审批禁止；批准前检查请假日期内已排服务；已实现在岗看板（在岗/请假/今日预约/下一预约）；仍无周排班表；
- 移动端“我的”有基础资料和请假入口；排班查看仍缺；
- 总部无跨店人力视图。

## 12. 非目标与开放问题

非目标：首版不做复杂工时薪酬计算。

🔵 OQ-05 排班由门店维护还是总部统一？
🔵 OQ：请假审批人是店长还是区域？
🔵 OQ：技师能否跨店服务？
🔶 假设：首版排班周视图，门店维护，总部只读。
