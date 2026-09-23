"""Shared validation for customer-authored feedback."""

from fastapi import HTTPException


TAG_GROUPS = {
    "positive": {"手法专业", "力度合适", "沟通细致", "环境舒适", "整体放松"},
    "neutral": {"手法一般", "力度需调整", "沟通可更清楚", "环境一般", "项目预期不一致"},
    "negative": {"力度不合适", "沟通体验不好", "等待较久", "环境问题", "项目与预期不符", "其他问题"},
}


def validate_feedback_tags(rating: int, tags: list[str]) -> None:
    allowed = TAG_GROUPS["positive" if rating >= 4 else "neutral" if rating == 3 else "negative"]
    if len(set(tags)) != len(tags) or any(tag not in allowed for tag in tags):
        raise HTTPException(
            status_code=400,
            detail={"code": "FEEDBACK_TAG_INVALID", "message": "评价标签与当前评分不匹配"},
        )
