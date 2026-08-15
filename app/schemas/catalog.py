from datetime import datetime

from pydantic import BaseModel


class StoreOut(BaseModel):
    id: int
    store_code: str
    name: str
    city: str = ""
    address: str = ""
    phone: str = ""
    business_hours: str = ""
    location_lat: float | None = None
    location_lng: float | None = None
    status: str

    model_config = {"from_attributes": True}


class PriceOut(BaseModel):
    price_type: str
    amount_cents: int

    model_config = {"from_attributes": True}


class ProjectOut(BaseModel):
    id: int
    code: str
    category: str
    category_mark: str = ""
    name: str
    duration_min: int | None = None
    summary: str = ""
    image_url: str = ""
    tags: list = []
    detail_modules: list = []
    diy_options: list = []
    display_order: int = 0
    price_label: str = ""
    prices: list[PriceOut] = []

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    items: list[ProjectOut]
    total: int
