"""统一会员确认价、目录选项收费解析。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import OptionChoicePrice, PriceBook, Project, ProjectOptionChoice


PriceBasis = Literal["store", "member", "tuesday_68", "annual_gift"]


@dataclass(frozen=True)
class ConfirmedPrice:
    amount_cents: int
    basis: PriceBasis


@dataclass(frozen=True)
class PriceContext:
    is_member: bool
    confirmed_at: datetime
    store_timezone: str


@dataclass(frozen=True)
class ResolvedCharge:
    amount_cents: int
    basis: str
    price_source: str
    source_ref: dict
    choice_snapshot: dict
    chargeable: bool
    annual_gift_candidate: bool = False


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _price_value(prices: dict[str, int | None], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = prices.get(key)
        if value is not None:
            return int(value)
    return None


def confirmed_price_for_line(
    prices: dict[str, int | None],
    is_member: bool,
    confirmed_at: datetime,
    store_timezone: str,
) -> ConfirmedPrice:
    """按门店时区和会员身份计算实际确认单价。"""
    store = _price_value(prices, ("store",))
    if store is None:
        raise ValueError("store price is required")
    if not is_member:
        return ConfirmedPrice(amount_cents=store, basis="store")

    member = _price_value(prices, ("member", "group", "store"))
    if member is None:
        raise ValueError("member price is required")

    local_confirmed_at = _aware(confirmed_at).astimezone(ZoneInfo(store_timezone))
    if local_confirmed_at.weekday() == 1:
        tuesday_amount = round(store * 0.68)
        if tuesday_amount < member:
            return ConfirmedPrice(amount_cents=tuesday_amount, basis="tuesday_68")
    return ConfirmedPrice(amount_cents=member, basis="member")


def price_book_prices(db: Session, project_id: int) -> dict[str, int]:
    rows = list(db.scalars(select(PriceBook).where(PriceBook.project_id == project_id)))
    by_type = {row.price_type: int(row.amount_cents) for row in rows}
    store = by_type.get("store")
    if store is None:
        fallback = _price_value(by_type, ("group", "member"))
        if fallback is None:
            raise ValueError(f"project {project_id} has no price")
        store = fallback
    return {
        "store": store,
        "group": by_type.get("group", store),
        "member": by_type.get("member", by_type.get("group", store)),
    }


def _choice_snapshot(choice: ProjectOptionChoice) -> dict:
    return {
        "id": choice.id,
        "code": choice.code,
        "name": choice.name,
        "choice_type": choice.choice_type,
        "linked_project_id": choice.linked_project_id,
        "charge_mode": choice.charge_mode,
        "coupon_eligible": choice.coupon_eligible,
        "annual_gift_eligible": choice.annual_gift_eligible,
        "qualifies_for_foot_bath_bundle": choice.qualifies_for_foot_bath_bundle,
        "status": choice.status,
    }


def _current_option_prices(
    db: Session,
    option_choice_id: int,
    confirmed_at: datetime,
) -> dict[str, int]:
    confirmed_at = _aware(confirmed_at)
    rows = list(db.scalars(
        select(OptionChoicePrice)
        .where(
            OptionChoicePrice.option_choice_id == option_choice_id,
            OptionChoicePrice.effective_from <= confirmed_at,
            or_(
                OptionChoicePrice.effective_to.is_(None),
                OptionChoicePrice.effective_to > confirmed_at,
            ),
        )
        .order_by(OptionChoicePrice.price_type, OptionChoicePrice.effective_from.desc())
    ))
    prices: dict[str, int] = {}
    for row in rows:
        prices.setdefault(row.price_type, int(row.amount_cents))
    store = prices.get("store")
    if store is None:
        raise ValueError(f"option choice {option_choice_id} has no active store price")
    return {
        "store": store,
        "group": prices.get("group", store),
        "member": prices.get("member", prices.get("group", store)),
    }


def resolve_option_charge(
    db: Session,
    choice_id: int,
    price_context: PriceContext,
) -> ResolvedCharge:
    """解析目录选项的服务端收费金额，不消费年度赠送权益。"""
    choice = db.get(ProjectOptionChoice, choice_id)
    if choice is None or choice.status != "active":
        raise ValueError(f"option choice {choice_id} is not active")

    snapshot = _choice_snapshot(choice)
    if choice.choice_type == "preference" or choice.charge_mode == "free":
        return ResolvedCharge(
            amount_cents=0,
            basis="free",
            price_source="free",
            source_ref={"option_choice_id": choice.id},
            choice_snapshot=snapshot,
            chargeable=False,
        )

    if choice.choice_type == "linked_project" or choice.charge_mode == "inherit_linked_price":
        if choice.linked_project_id is None:
            raise ValueError(f"linked option choice {choice_id} has no linked project")
        linked = db.get(Project, choice.linked_project_id)
        if linked is None:
            raise ValueError(f"linked project {choice.linked_project_id} does not exist")
        prices = price_book_prices(db, linked.id)
        confirmed = confirmed_price_for_line(
            prices,
            price_context.is_member,
            price_context.confirmed_at,
            price_context.store_timezone,
        )
        return ResolvedCharge(
            amount_cents=confirmed.amount_cents,
            basis=confirmed.basis,
            price_source="linked_project",
            source_ref={
                "option_choice_id": choice.id,
                "price_book_project_id": linked.id,
                "project_code": linked.code,
            },
            choice_snapshot=snapshot,
            chargeable=True,
            annual_gift_candidate=bool(choice.annual_gift_eligible and confirmed.amount_cents <= 9900),
        )

    if choice.choice_type == "dedicated_charge" or choice.charge_mode == "custom_price":
        prices = _current_option_prices(db, choice.id, price_context.confirmed_at)
        confirmed = confirmed_price_for_line(
            prices,
            price_context.is_member,
            price_context.confirmed_at,
            price_context.store_timezone,
        )
        return ResolvedCharge(
            amount_cents=confirmed.amount_cents,
            basis=confirmed.basis,
            price_source="option_choice_price",
            source_ref={"option_choice_id": choice.id},
            choice_snapshot=snapshot,
            chargeable=True,
            annual_gift_candidate=bool(choice.annual_gift_eligible and confirmed.amount_cents <= 9900),
        )

    raise ValueError(f"unsupported option charge mode for choice {choice_id}")
