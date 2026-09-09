# 管理端经营报表 v1

## 读取接口

`GET /api/v1/admin/operations-summary` 继续使用既有日期参数与门店范围校验；仅当前门店的管理角色可读取，普通员工与跨店请求保持拒绝。

新增两个只读字段：

```json
{
  "project_sales_top5": [
    {"name": "肩颈调理", "quantity": 3}
  ],
  "technician_service_counts": [
    {"technician_id": 12, "name": "技师甲", "completed_services_count": 2}
  ]
}
```

## 统计口径与隐私边界

- 仅统计本店且 `actual_service_end_at` 在请求日期范围内的已结束服务位。
- `project_sales_top5` 汇总关联选单已保存的项目名称与正整数数量，按数量降序、名称升序返回最多五项；不读取目录当前名称、价格或顾客信息。
- `technician_service_counts` 按服务位的 `serviced_by_technician_id` 汇总，按完成服务数降序、姓名与 ID 稳定排序返回最多五项。
- 未归属、跨店、缺失技师档案或没有结束时间的记录不进入技师服务量；不得猜测归属。
- 响应不包含手机号、顾客、会员、价格、提成、服务参考或其他自由文本。

本契约不增加导出、跨店汇总、财务结算、数据库迁移或智慧宝物理资源操作。
