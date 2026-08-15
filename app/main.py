from fastapi import FastAPI

from app.api import admin, admin_catalog, admin_v2, auth, catalog, coupons, health, integrations, occupancies, operations, orders, payments, selections, tracking
from app.core.config import settings
from app.release_static import mount_release_static_files

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="荷小悦顾客端 API（FastAPI + PostgreSQL）",
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    redoc_url=None,
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(integrations.router, prefix="/api/v1")
app.include_router(catalog.router, prefix="/api/v1")
app.include_router(orders.router, prefix="/api/v1")
app.include_router(payments.router, prefix="/api/v1")
app.include_router(coupons.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(tracking.router, prefix="/api/v1")
app.include_router(admin_v2.router, prefix="/api/v1")
app.include_router(admin_catalog.router, prefix="/api/v1")
app.include_router(operations.router, prefix="/api/v1")
app.include_router(selections.router, prefix="/api/v1")
app.include_router(occupancies.router, prefix="/api/v1")
mount_release_static_files(app)
