"""Read-only projection of a customer's own source membership.

Only the authenticated customer's ``MembershipCard`` snapshots are read.
No card, balance, wallet, order or audit row is written here. Existing
``balance_cents`` is exposed as a source snapshot, never as real-time balance
or as a proven principal/gift split.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.membership_entitlements import card_state, membership_snapshot
from app.models import MembershipCard, Store, User
from app.core.config import settings


ANNUAL_BENEFITS = (
    "会员价",
    "周二会员活动（按门店价消费主项买一赠一；适用主项、赠送搭配、补差和叠加由门店确认）",
    "开卡赠礼（是否已登记/发放以门店记录为准）",
)
STORED_BENEFITS = (
    "会员价",
    "周二会员活动（按门店价消费主项买一赠一；适用主项、赠送搭配、补差和叠加由门店确认）",
    "储值余额用尽后会员权益失效（以本店有效卡判定为准）",
    "开卡赠品（如有，以门店记录为准）",
)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    current = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return current.isoformat()


def _source_balance(card: MembershipCard) -> dict:
    if card.card_type != "stored":
        return {
            "status": "not_applicable",
            "amount_cents": None,
            "real_time": False,
            "observed_at": None,
            "split": "not_applicable",
            "semantics": "annual_card_has_no_stored_balance",
        }
    return {
        "status": "source_snapshot",
        "amount_cents": int(card.balance_cents),
        "real_time": False,
        "observed_at": _iso(card.observed_at),
        "split": "unverified",
        "semantics": "source_snapshot_total_not_proven_principal_or_bonus",
    }


def build_customer_membership_overview(db: Session, user: User) -> dict:
    # Explicit, verified source scope. Legacy user.membership_store_id is not
    # an entitlement restriction and must not hide real cards for this source.
    card_query = select(MembershipCard).where(
        MembershipCard.user_id == user.id,
        MembershipCard.source == settings.member_source,
        MembershipCard.store_id == settings.member_source_store_id,
    )
    cards = list(db.scalars(card_query.order_by(MembershipCard.store_id, MembershipCard.started_at, MembershipCard.id)))
    store_names = {
        store.id: store.name
        for store in db.scalars(select(Store).where(Store.id.in_({card.store_id for card in cards})))
    } if cards else {}
    now = datetime.now(UTC)
    card_items = []
    observed_values = []
    for card in cards:
        state = card_state(card, now)
        observed = _iso(card.observed_at)
        if observed and card.card_type == "stored":
            observed_values.append(card.observed_at)
        card_items.append({
            "id": card.id,
            "card_type": card.card_type,
            "card_type_label": "年度权益卡" if card.card_type == "annual" else "储值会员卡",
            "status": state,
            "usable": state == "active",
            "store_id": card.store_id,
            "store_name": store_names.get(card.store_id),
            "started_at": _iso(card.started_at),
            "expires_at": _iso(card.expires_at),
            "source": card.source,
            "observed_at": observed,
            "balance": _source_balance(card),
            "benefits": list(ANNUAL_BENEFITS if card.card_type == "annual" else STORED_BENEFITS),
            "benefits_note": "权益以本店有效卡和门店人工确认为准。",
        })
    # Reuse the existing global entitlement union; do not maintain a second
    # card-validity algorithm just for presentation.
    identity = membership_snapshot(db, user)
    return {
        "identity": {
            "is_member": bool(identity.get("is_member")),
            "member_type": identity.get("member_type"),
            "member_expire_at": _iso(identity.get("member_expire_at")),
            "note": "会员身份来自既有本人登录和来源卡判定，不是历史会员标签。",
        },
        "cards": card_items,
        "card_count": len(card_items),
        "coverage": {
            "source": settings.member_source,
            "store_ids": [settings.member_source_store_id],
            "returned_store_ids": sorted({card.store_id for card in cards}),
            "card_snapshot": "returned" if card_items else "no_source_card",
            "history": "unverified",
            "history_reason": "来源消费历史字段/完整分页尚未核验，未导入任何账单。",
            "as_of": _iso(max(observed_values)) if observed_values else None,
        },
        "consumption": {
            "status": "unverified",
            "amount_cents": None,
            "bill_count": None,
            "coverage": None,
            "label": "未核实",
            "note": "没有已核验的历史账单；不显示 0 或推算金额。",
        },
        "savings": {
            "status": "unverified",
            "amount_cents": None,
            "coverage": None,
            "label": "累计消费优惠未核实",
            "note": "历史门店价、结算额、支付构成和退款关联未完成来源核验前，不计算优惠。",
        },
        "generated_at": now.isoformat(),
        "read_only": True,
    }
