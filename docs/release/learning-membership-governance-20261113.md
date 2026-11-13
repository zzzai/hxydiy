# 学习治理与会员只读状态（2026-11-13）

- PR #487 合并 `330879aff11ba2cc64de68a1624bb9b302e3a27b`；CI 43374072137 success；Deploy 43374976600 success；current `github-330879aff11b-43374976600`。
- 学习：`GET /admin/v2/learning/overview` 只读课程版本/进度/AI审计；页面 `/admin/#/learning-admin` 仅总部管理员可见。
- 会员：`GET /admin/v2/membership/overview` 只读旧标记/来源卡/到期；`sync_status=unverified`，不使用私有导入输入。
- 生产只读核验课程12个、AI调用8次/7257 tokens/失败1次；会员330顾客/102有效卡；无业务写入。
- 无迁移；回退到前一应用 release，旧数据、旧课程、旧会员卡和历史记录不删。
- 未完成：经营分析数据源口径整合、自动化执行器、真实学习任务/评分验收。
