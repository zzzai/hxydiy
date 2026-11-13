"""Validation and display contracts for coupon templates.

`percent_off` is the percentage removed from the order total.  It is not a
Chinese discount rate: 20 means 20% off (8折), 50 means half price (5折).
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException

VALID_COUPON_TYPES = {"fixed", "percent"}
VALID_COUPON_STATUSES = {"draft", "published", "archived"}
_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")


def coupon_config_errors(values: dict[str, Any]) -> list[dict[str, str]]:
    """Return field-level errors without mutating a template."""
    errors: list[dict[str, str]] = []
    code = str(values.get("code") or "").strip()
    if not _CODE_RE.fullmatch(code):
        errors.append({"field": "code", "message": "编码只能包含字母、数字、点、横线或下划线，长度 1-32"})
    name = str(values.get("name") or "").strip()
    if not 1 <= len(name) <= 64:
        errors.append({"field": "name", "message": "名称长度需为 1-64 个字符"})
    coupon_type = values.get("coupon_type")
    if coupon_type not in VALID_COUPON_TYPES:
        errors.append({"field": "coupon_type", "message": "券类型只能是 fixed 或 percent"})
    status = values.get("status")
    if status not in VALID_COUPON_STATUSES:
        errors.append({"field": "status", "message": "状态只能是 draft、published 或 archived"})

    amount = values.get("amount_cents")
    if not isinstance(amount, int) or isinstance(amount, bool):
        errors.append({"field": "amount_cents", "message": "固定面额必须是以分为单位的整数"})
    elif coupon_type == "fixed" and amount <= 0:
        errors.append({"field": "amount_cents", "message": "固定面额券的面额必须大于 0"})

    percent = values.get("percent_off")
    if coupon_type == "percent":
        if not isinstance(percent, int) or isinstance(percent, bool) or not 1 <= percent <= 100:
            errors.append({"field": "percent_off", "message": "减免比例必须是 1-100 的整数"})

    for field, label, maximum in (
        ("min_spend_cents", "使用门槛", 100_000_000),
        ("validity_days", "有效期", 3650),
        ("claim_limit", "每人限领", 100_000),
    ):
        value = values.get(field)
        minimum = 1 if field == "validity_days" else 0
        if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
            errors.append({"field": field, "message": f"{label}必须是 {minimum}-{maximum} 的整数"})

    budget = values.get("budget_cents")
    if budget is not None and (not isinstance(budget, int) or isinstance(budget, bool) or budget < 0):
        errors.append({"field": "budget_cents", "message": "预算必须为空或大于等于 0（0 表示零预算）"})
    return errors


def require_valid_coupon_config(values: dict[str, Any]) -> None:
    errors = coupon_config_errors(values)
    if errors:
        raise HTTPException(status_code=422, detail={
            "code": "COUPON_CONFIG_INVALID",
            "message": "券配置不完整或数值不合法",
            "fields": errors,
        })


def coupon_config_warnings(template: Any) -> list[str]:
    """Diagnostics for legacy rows; never used to rewrite stored data."""
    warnings: list[str] = []
    if template.coupon_type == "percent" and template.percent_off is None:
        warnings.append("折扣券缺少减免比例")
    if template.coupon_type == "fixed" and (template.amount_cents or 0) <= 0:
        warnings.append("固定面额券面额无效")
    return warnings
