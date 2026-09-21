# 服务位维修备注与展示顺序 v1

## 目的与边界

本契约仅覆盖 DIY 管理后台中实际服务位的静态配置。它不改变 `operational_status`、占用、服务单、二维码、顾客扫码、地图坐标或智慧宝的开房、开沙发、派钟、离位、清洁及物理资源释放。

本期不提供总部跨店选店与编辑；调用方必须是绑定门店的店长。历史 `admin` 账号如已绑定门店，会按既有兼容规则作为店长处理。

## 写接口

`PATCH /api/v1/admin/service-positions/{room_id}/configuration`

请求体严格只接受以下字段，至少提供一个：

```json
{
  "maintenance_note": "靠窗插座待检修",
  "display_order": 3
}
```

- `maintenance_note`：字符串，最长 256 字；空字符串清空；不接受 `null`。
- `display_order`：非负整数；不接受小数或 `null`。
- 未知字段、空请求、负数、超长文本、`null` 均为 `422`。

成功响应：

```json
{
  "id": 17,
  "maintenance_note": "靠窗插座待检修",
  "display_order": 3
}
```

服务端将两个公开字段分别映射到既有 `Room.note` 与 `Room.sort_order`，不新增数据库列或迁移。仅 `is_service_position=true` 且 `is_space_container=false` 的服务位可更新；空间容器或非服务位返回 `400`。店长只能匹配本店服务位，跨店或不存在目标返回 `404`。普通员工由请求级只读白名单拒绝为 `403 STAFF_READ_ONLY`；其他非店长角色返回 `403 MANAGER_REQUIRED`。

每次成功请求均新增 `service_position_configuration_updated` 审计记录，包含操作者、门店、服务位 ID 及 `before`/`after` 的备注和顺序值。

## 读取与前端

`GET /api/v1/admin/live-service-position-map` 继续按 `sort_order, id` 返回服务位。绑定门店店长的响应包含 `maintenance_note`；普通员工响应不包含该字段，以维持最小可见范围。管理端仅为已绑定门店的店长显示编辑控件；普通员工没有备注显示或写入口。

1 号店沙发的稳定编码继续使用 `sofa-01` 至 `sofa-08`，编码用于二维码和历史关联，不随门店物理编号调整。顾客显示号映射为：`sofa-01 → 1号`、`sofa-02 → 2号`、`sofa-03 → 3号`、`sofa-04 → 5号`、`sofa-05 → 6号`、`sofa-06 → 7号`、`sofa-07 → 8号`、`sofa-08 → 9号`。顾客端平面图按 `map_x` 区分左右区域、按 `map_y` 决定同侧上下顺序。

既有启停接口 `/api/v1/admin/service-positions/{room_id}/operational-status`、二维码接口和占用流程保持不变。维护备注或展示顺序的变更不因服务位当前占用而改写、结束或拒绝现场服务。
