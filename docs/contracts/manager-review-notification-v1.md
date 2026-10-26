# 店长评价通知契约 v1

- 提交路由不新增顾客字段；VisitFeedback 成功 commit/refresh 后仅新记录安排 notify_visit_feedback；已有幂等返回和并发唯一约束回退均不重复安排。
- service_review 指向 ServiceFeedback，visit_feedback 指向 VisitFeedback。回跳为 `/technician/store/wecom?review=<type>:<id>`；前端只接受安全正整数，不使用数字 ID 推断表。
- GET/PATCH `/admin/v2/feedback/<type>/<id>` 保持当前鉴权及 store_id 约束；列表不传 feedback_type 时混合两来源；低分待办传 low_rating_only=true 和 follow_up_status=open。
- 接收范围沿用 `WECOM_ORDER_NOTIFY_USERIDS` 与当前企业 ID、同店有效 manager/绑定/唯一管理工作区的交集；发送时重新核验有效身份及临时有效期。新扫码入口额外要求 `WECOM_VISIT_FEEDBACK_NOTIFY_ENABLED=true`。
- 审计 action=wecom_feedback_notify，entity_type=service_feedback/visit_feedback，detail 仅含 attempt_id、status 和人数；started 为发送前事实，accepted/partial/rejected 为 provider 回执，unknown 为无法确认，no_recipient 为没有合格接收人。只追加审计，不将其改造成任务队列。
- accepted 不等于已读；超时可能已受理，因此不进行无依据自动重发。本批不提供持久补偿、历史回放或数据库迁移。
