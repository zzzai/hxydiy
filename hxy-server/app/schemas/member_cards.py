from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator


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


class MemberCardFactUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    balance_cents: StrictInt | None = Field(default=None, ge=0, le=2**31 - 1)
    status: Literal["active", "disabled"] | None = None
    observed_at: datetime
    evidence: str = Field(min_length=2, max_length=300)
    reason: str = Field(min_length=2, max_length=200)
    apply: StrictBool = False
    expected_version: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    preview_token: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")

    @field_validator("observed_at")
    @classmethod
    def aware_observation(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def require_controlled_update(self):
        if self.balance_cents is None and self.status is None:
            raise ValueError("balance_cents or status is required")
        if self.apply and not all((self.expected_version, self.preview_token, self.idempotency_key)):
            raise ValueError("apply requires version, preview token and idempotency key")
        return self
