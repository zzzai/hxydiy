from fastapi import FastAPI

from app.api import admin, auth, catalog, coupons, health, orders, payments
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="荷小悦顾客端 API（FastAPI + PostgreSQL）",
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(catalog.router, prefix="/api/v1")
app.include_router(orders.router, prefix="/api/v1")
app.include_router(payments.router, prefix="/api/v1")
app.include_router(coupons.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
