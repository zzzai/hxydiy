from datetime import datetime

from pydantic import BaseModel, Field


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
    tags: list = Field(default_factory=list)
    detail_modules: list = Field(default_factory=list)
    diy_options: list = Field(default_factory=list)
    display_order: int = 0
    price_label: str = ""
    prices: list[PriceOut] = Field(default_factory=list)
    catalog_version: int | None = None
    catalog_version_id: int | None = None
    option_groups: list = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    items: list[ProjectOut]
    total: int
