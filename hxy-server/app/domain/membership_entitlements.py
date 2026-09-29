"""Resolve current rights without mutating identity, wallet or frozen prices."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.models.membership import MembershipCard


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def legacy_membership_active(user: User, now: datetime) -> bool:
    if not user.is_member:
        return False
    if user.member_type == "annual" and user.member_expire_at is None:
        return False
    if user.member_expire_at is not None and _utc(user.member_expire_at) <= _utc(now):
        return False
    if user.member_type == "stored" and (user.balance_cents or 0) <= 0:
        return False
    return True


def card_state(card: MembershipCard, now: datetime) -> str:
    current = _utc(now)
    if card.status != "active":
        return "disabled"
    if _utc(card.started_at) > current:
        return "scheduled"
    if card.expires_at is not None and _utc(card.expires_at) <= current:
        return "expired"
    if card.card_type == "annual" and card.expires_at is None:
        return "invalid"
    if card.card_type == "stored" and card.balance_cents <= 0:
        return "exhausted"
    return "active"


def active_cards(
    db: Session, user: User | None, *, store_id: int | None = None,
    now: datetime | None = None,
) -> list[MembershipCard]:
    if user is None:
        return []
    current = _utc(now or datetime.now(UTC))
    query = select(MembershipCard).where(
        MembershipCard.user_id == user.id, MembershipCard.status == "active",
    )
    if store_id is not None:
        query = query.where(MembershipCard.store_id == store_id)
    return [card for card in db.scalars(query) if card_state(card, current) == "active"]


def has_membership(
    db: Session, user: User | None, *, store_id: int | None = None,
    now: datetime | None = None,
) -> bool:
    current = now or datetime.now(UTC)
    return bool(user and (legacy_membership_active(user, current) or active_cards(
        db, user, store_id=store_id, now=current,
    )))


def membership_snapshot(db: Session, user: User) -> dict:
    current = datetime.now(UTC)
    if legacy_membership_active(user, current):
        return {"is_member": True, "member_type": user.member_type, "member_expire_at": user.member_expire_at}
    cards = active_cards(db, user, now=current)
    annual = [card for card in cards if card.card_type == "annual"]
    selected = max(annual, key=lambda card: _utc(card.expires_at)) if annual else next(iter(cards), None)
    return {"is_member": bool(selected), "member_type": selected.card_type if selected else None,
            "member_expire_at": selected.expires_at if selected else None}
