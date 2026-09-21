from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator


class ProductDetailModule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["text", "image"]
    title: StrictStr = Field(default="", max_length=128)
    body: StrictStr = Field(default="", max_length=2000)
    image_url: StrictStr = Field(default="", max_length=512)

    @model_validator(mode="after")
    def validate_content(self):
        if self.type == "text" and not self.body.strip():
            raise ValueError("text detail module requires body")
        if self.type == "image" and not self.image_url.strip():
            raise ValueError("image detail module requires image_url")
        return self


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
