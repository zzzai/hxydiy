"""统一会员确认价、目录选项收费解析。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import OptionChoicePrice, PriceBook, Project, ProjectOptionChoice
from app.domain.catalog_options import choice_contract_errors


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
    member_expire_at: datetime | None = None
    member_type: str | None = None
    store_id: int | None = None


@dataclass(frozen=True)
class ResolvedCharge:
    amount_cents: int
    basis: str
    price_source: str
    source_ref: dict
    choice_snapshot: dict
    chargeable: bool
    prices: dict[str, int]
    confirmed_price: ConfirmedPrice | None

    def ordinary_coupon_payable_cents(self, discount_cents: int) -> int:
        """普通券从门店价抵扣，但券后价不得低于会员价。"""
        if not self.chargeable:
            return 0
        store = int(self.prices.get("store", self.amount_cents))
        member = int(self.prices.get("member", store))
        return max(member, store - max(0, int(discount_cents)))


@dataclass(frozen=True)
class PriceBookSnapshot:
    prices: dict[str, int]
    id_by_type: dict[str, int]
    version_by_type: dict[str, str]
    source_type_by_price_key: dict[str, str]


@dataclass(frozen=True)
class OptionChoicePriceSnapshot:
    prices: dict[str, int]
    id_by_type: dict[str, int]
    effective_from_by_type: dict[str, str]
    source_type_by_price_key: dict[str, str]


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("confirmed_at must be timezone-aware")
    return value


def _membership_is_active(
    is_member: bool,
    member_expire_at: datetime | None,
    confirmed_at: datetime,
    member_type: str | None = None,
) -> bool:
    if not is_member:
        return False
    if member_type == "annual" and member_expire_at is None:
        # 旧年度会员缺少到期日时不能被当作永久会员；保留记录供后台补正，
        # 但确认价必须按门店价结算。
        return False
    if member_expire_at is None:
        # 兼容尚未补齐到期日的历史非年度会员；新年度卡由 API 强制带到期日。
        return True
    return _aware(member_expire_at).astimezone(ZoneInfo("UTC")) > _aware(confirmed_at).astimezone(ZoneInfo("UTC"))


def _store_zone(store_timezone: str) -> ZoneInfo:
    try:
        return ZoneInfo(store_timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"invalid store timezone: {store_timezone}") from exc


def _price_value(prices: dict[str, int | None], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = prices.get(key)
        if value is not None:
            return int(value)
    return None


def _source_key_for_basis(basis: str) -> str:
    if basis == "tuesday_68":
        return "store"
    return basis


def confirmed_price_for_line(
    prices: dict[str, int | None],
    is_member: bool,
    confirmed_at: datetime,
    store_timezone: str,
    member_expire_at: datetime | None = None,
    member_type: str | None = None,
) -> ConfirmedPrice:
    """按门店时区和会员身份计算实际确认单价。"""
    store = _price_value(prices, ("store",))
    if store is None:
        raise ValueError("store price is required")
    local_confirmed_at = _aware(confirmed_at).astimezone(_store_zone(store_timezone))
    if not _membership_is_active(is_member, member_expire_at, confirmed_at, member_type):
        return ConfirmedPrice(amount_cents=store, basis="store")

    member = _price_value(prices, ("member", "group", "store"))
    if member is None:
        raise ValueError("member price is required")

    if member_type == "annual" and local_confirmed_at.weekday() == 1:
        tuesday_amount = round(store * 0.68)
        if tuesday_amount < member:
            return ConfirmedPrice(amount_cents=tuesday_amount, basis="tuesday_68")
    return ConfirmedPrice(amount_cents=member, basis="member")


def price_book_snapshot(db: Session, project_id: int) -> PriceBookSnapshot:
    now = datetime.now(UTC)
    rows = list(db.scalars(
        select(PriceBook)
        .where(
            PriceBook.project_id == project_id,
            or_(PriceBook.effective_to.is_(None), PriceBook.effective_to > now),
        )
        .order_by(PriceBook.price_type, PriceBook.published_at.desc(), PriceBook.id.desc())
    ))
    by_type: dict[str, int] = {}
    id_by_type: dict[str, int] = {}
    version_by_type: dict[str, str] = {}
    for row in rows:
        if row.price_type in by_type:
            continue
        by_type[row.price_type] = int(row.amount_cents)
        id_by_type[row.price_type] = int(row.id)
        version_by_type[row.price_type] = row.version
    store = by_type.get("store")
    if store is None:
        raise ValueError(f"store price is required for project {project_id}")
    prices = {
        "store": store,
        "group": by_type.get("group", store),
        "member": by_type.get("member", by_type.get("group", store)),
    }
    source_type_by_price_key = {
        "store": "store",
        "group": "group" if "group" in by_type else "store",
        "member": "member" if "member" in by_type else ("group" if "group" in by_type else "store"),
    }
    return PriceBookSnapshot(
        prices=prices,
        id_by_type=id_by_type,
        version_by_type=version_by_type,
        source_type_by_price_key=source_type_by_price_key,
    )


def price_book_prices(db: Session, project_id: int) -> dict[str, int]:
    return price_book_snapshot(db, project_id).prices


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
) -> OptionChoicePriceSnapshot:
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
        .order_by(OptionChoicePrice.price_type, OptionChoicePrice.effective_from.desc(), OptionChoicePrice.id.desc())
    ))
    prices: dict[str, int] = {}
    id_by_type: dict[str, int] = {}
    effective_from_by_type: dict[str, str] = {}
    for row in rows:
        if row.price_type in prices:
            continue
        prices[row.price_type] = int(row.amount_cents)
        id_by_type[row.price_type] = int(row.id)
        effective_from_by_type[row.price_type] = row.effective_from.isoformat()
    store = prices.get("store")
    if store is None:
        raise ValueError(f"option choice {option_choice_id} has no active store price")
    normalized_prices = {
        "store": store,
        "group": prices.get("group", store),
        "member": prices.get("member", prices.get("group", store)),
    }
    source_type_by_price_key = {
        "store": "store",
        "group": "group" if "group" in prices else "store",
        "member": "member" if "member" in prices else ("group" if "group" in prices else "store"),
    }
    return OptionChoicePriceSnapshot(
        prices=normalized_prices,
        id_by_type=id_by_type,
        effective_from_by_type=effective_from_by_type,
        source_type_by_price_key=source_type_by_price_key,
    )


def resolve_option_charge(
    db: Session,
    choice_id: int,
    price_context: PriceContext,
) -> ResolvedCharge:
    """解析目录选项的服务端收费金额，不消费年度赠送权益。"""
    choice = db.get(ProjectOptionChoice, choice_id)
    if choice is None or choice.status != "active":
        raise ValueError(f"option choice {choice_id} is not active")

    has_local_prices = db.scalar(
        select(OptionChoicePrice.id)
        .where(OptionChoicePrice.option_choice_id == choice.id)
        .limit(1)
    ) is not None
    contract_errors = choice_contract_errors(
        choice,
        has_local_prices=has_local_prices,
        path=f"choices.{choice.code}",
    )
    if contract_errors:
        raise ValueError(f"invalid option choice contract: {contract_errors[0].code}")

    snapshot = _choice_snapshot(choice)
    if choice.choice_type == "preference":
        return ResolvedCharge(
            amount_cents=0,
            basis="free",
            price_source="free",
            source_ref={"option_choice_id": choice.id},
            choice_snapshot=snapshot,
            chargeable=False,
            prices={"store": 0, "group": 0, "member": 0},
            confirmed_price=None,
        )

    if choice.choice_type == "linked_project":
        if choice.linked_project_id is None:
            raise ValueError(f"linked option choice {choice_id} has no linked project")
        linked = db.get(Project, choice.linked_project_id)
        if linked is None:
            raise ValueError(f"linked project {choice.linked_project_id} does not exist")
        price_snapshot = price_book_snapshot(db, linked.id)
        confirmed = confirmed_price_for_line(
            price_snapshot.prices,
            price_context.is_member,
            price_context.confirmed_at,
            price_context.store_timezone,
            price_context.member_expire_at,
            price_context.member_type,
        )
        confirmed_source_type = price_snapshot.source_type_by_price_key[_source_key_for_basis(confirmed.basis)]
        return ResolvedCharge(
            amount_cents=confirmed.amount_cents,
            basis=confirmed.basis,
            price_source="linked_project",
            source_ref={
                "option_choice_id": choice.id,
                "price_book_project_id": linked.id,
                "project_code": linked.code,
                "price_book_id_by_type": price_snapshot.id_by_type,
                "price_book_version_by_type": price_snapshot.version_by_type,
                "price_book_source_type_by_price_key": price_snapshot.source_type_by_price_key,
                "confirmed_price_source_type": confirmed_source_type,
                "confirmed_price_book_id": price_snapshot.id_by_type[confirmed_source_type],
                "confirmed_price_book_version": price_snapshot.version_by_type[confirmed_source_type],
            },
            choice_snapshot=snapshot,
            chargeable=True,
            prices=price_snapshot.prices,
            confirmed_price=confirmed,
        )

    if choice.choice_type == "dedicated_charge":
        price_snapshot = _current_option_prices(db, choice.id, price_context.confirmed_at)
        confirmed = confirmed_price_for_line(
            price_snapshot.prices,
            price_context.is_member,
            price_context.confirmed_at,
            price_context.store_timezone,
            price_context.member_expire_at,
            price_context.member_type,
        )
        confirmed_source_type = price_snapshot.source_type_by_price_key[_source_key_for_basis(confirmed.basis)]
        return ResolvedCharge(
            amount_cents=confirmed.amount_cents,
            basis=confirmed.basis,
            price_source="option_choice_price",
            source_ref={
                "option_choice_id": choice.id,
                "option_choice_price_id_by_type": price_snapshot.id_by_type,
                "option_choice_price_effective_from_by_type": price_snapshot.effective_from_by_type,
                "option_choice_price_source_type_by_price_key": price_snapshot.source_type_by_price_key,
                "confirmed_price_source_type": confirmed_source_type,
                "confirmed_option_choice_price_id": price_snapshot.id_by_type[confirmed_source_type],
                "confirmed_option_choice_price_effective_from": (
                    price_snapshot.effective_from_by_type[confirmed_source_type]
                ),
            },
            choice_snapshot=snapshot,
            chargeable=True,
            prices=price_snapshot.prices,
            confirmed_price=confirmed,
        )

    raise ValueError(f"unsupported option charge mode for choice {choice_id}")
