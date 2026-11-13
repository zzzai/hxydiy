# 券报表北京时间自然日（2026-11-13）

- PR #491 合并 `5b77cde049d5ba1f06b881f485eb5a6f3a4da81b`；CI 43382303392 success；Deploy 43382920670 success；current `github-5b77cde049d5-43382920670`。
- 概览/核销记录支持可选 `start_date/end_date`，按 Asia/Shanghai 自然日换算为 UTC 半开区间；默认 `days` 仍是 UTC 滚动窗口。
- 测试覆盖北京零点前后、UTC 兼容、缺日期 422、90 天上限；前端日期选择已接通。
- 生产只读核验返回正确的 `utc_start_at/utc_end_at` 和两种 period mode；无业务写入。
- 无迁移；回退应用版本即可，历史券/核销/数据不动。
- 未完成：真实门店财务口径、课程/题库写入、自动化执行器。
