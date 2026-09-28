from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class MemberCardExplanation(BaseModel):
    source: str
    card_type: Literal["annual", "stored"]
    state: Literal["active", "disabled", "scheduled", "expired", "invalid", "exhausted"]
    started_at: datetime
    expires_at: datetime | None
    balance_cents: int
    balance_realtime: Literal[False] = False
    recorded_at: datetime


class MembershipExplanation(BaseModel):
    active: bool
    store_id: int
    legacy_active: bool
    cards: list[MemberCardExplanation]
