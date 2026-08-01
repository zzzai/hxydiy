from datetime import datetime

from pydantic import BaseModel


class OrderItemIn(BaseModel):
    project_id: int
    quantity: int = 1
    addon_ids: list[int] = []


class OrderCreate(BaseModel):
    order_type: str = "service"  # service / product / member
    items: list[OrderItemIn] = []
    member_plan_id: int | None = None  # order_type=member 时必填
    store_id: int
    booking_date: str | None = None
    booking_time: str | None = None
    coupon_id: int | None = None


class OrderItemOut(BaseModel):
    project_id: int | None = None
    name: str
    unit_price_cents: int
    quantity: int
    subtotal_cents: int


class OrderOut(BaseModel):
    id: int
    order_no: str
    order_type: str
    status: str
    pay_status: str
    pay_amount_cents: int
    total_amount_cents: int
    discount_cents: int = 0
    items: list = []
    booking_date: str | None = None
    booking_time: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CreateOrderResponse(BaseModel):
    code: int = 0
    data: OrderOut
