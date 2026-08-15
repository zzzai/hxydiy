# SCRM 模块：用户标签、分层、自动化营销规则

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CustomerTag(Base):
    """用户标签定义：标签名、颜色、类型（手动/自动）、自动打标规则"""

    __tablename__ = "customer_tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    color: Mapped[str] = mapped_column(String(7), default="#1f8f75")  # hex 色值
    tag_type: Mapped[str] = mapped_column(String(16), default="manual")  # manual / auto
    description: Mapped[str] = mapped_column(String(128), default="")
    # 自动打标规则（JSON），如：
    # {"event": "create_order", "count_gt": 3, "days": 30}  → 近 30 天下单 > 3 次 → "高频顾客"
    # {"event": "page_view", "project_category": "bath"}      → 浏览过沐足 → "沐足意向"
    auto_rule: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active / archived
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CustomerTagRelation(Base):
    """用户-标签 关联（多对多）"""

    __tablename__ = "customer_tag_relations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("customer_tags.id"), index=True)
    source: Mapped[str] = mapped_column(String(16), default="manual")  # manual / auto
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CustomerSegment(Base):
    """用户分层 / 分群：按条件组合圈定人群"""

    __tablename__ = "customer_segments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(256), default="")
    # 条件 JSON，如：
    # {"tags": ["高频顾客"], "member": true, "last_order_days": 30, "total_spend_gt": 50000}
    # {"tags": ["流失风险"], "last_visit_days_gt": 30}
    conditions: Mapped[dict] = mapped_column(JSON, default=dict)
    user_count: Mapped[int] = mapped_column(Integer, default=0)  # 符合条件的人数（定时计算）
    status: Mapped[str] = mapped_column(String(16), default="active")  # active / archived
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AutomationRule(Base):
    """SCRM 自动化规则：触发条件 → 执行动作"""

    __tablename__ = "automation_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(String(256), default="")
    trigger_event: Mapped[str] = mapped_column(String(32), index=True)
    # 触发事件：new_user(新用户注册) / first_order(首单) / order_completed(服务完成)
    #            no_visit_30d(30天未访问) / birthday(生日) / member_expiring(会员即将到期)
    # 条件（可选）：{"segment_id": 3, "tag": "高频顾客"}
    conditions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 动作列表，如：[{"type": "grant_coupon", "template_code": "comeback-500"}, {"type": "add_tag", "tag_id": 5}]
    # 动作类型：grant_coupon(发券) / add_tag(打标) / remove_tag(移除标签) / send_notification(微信通知，后续)
    actions: Mapped[list] = mapped_column(JSON, default=list)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    cooldown_days: Mapped[int] = mapped_column(Integer, default=0)  # 冷却期（天，同一用户触达间隔）
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trigger_count: Mapped[int] = mapped_column(Integer, default=0)  # 累计触发次数
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AutomationLog(Base):
    """自动化规则执行日志"""

    __tablename__ = "automation_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("automation_rules.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action_type: Mapped[str] = mapped_column(String(32))
    action_detail: Mapped[dict] = mapped_column(JSON, default=dict)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
