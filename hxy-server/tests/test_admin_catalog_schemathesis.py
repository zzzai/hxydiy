import pytest
import schemathesis
from hypothesis import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import Product, Project, Staff, Store


@pytest.fixture
def catalog_contract_context():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    with session_factory() as db:
        store = Store(
            store_code="contract-store",
            name="契约测试门店",
            city="安阳",
            address="测试地址",
            status="open",
        )
        staff = Staff(
            username="contract-headquarters",
            password_hash=hash_password("contract-pass"),
            name="契约测试总部",
            role="admin",
            store_id=None,
            status="active",
        )
        db.add_all([store, staff])
        db.flush()
        db.add_all([
            Project(
                store_id=store.id,
                code="SCHEMA-PROJECT",
                category="bath",
                name="契约项目",
                publication_status="draft",
            ),
            Product(
                store_id=store.id,
                code="SCHEMA-PRODUCT",
                name="契约商品",
                product_type="foot",
                price_cents=990,
                publication_status="draft",
            ),
        ])
        db.commit()
        token = create_staff_token(staff.id, staff.role)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.openapi_schema = None
    try:
        yield {"authorization": f"Bearer {token}"}
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.openapi_schema = None
        engine.dispose()


@pytest.fixture
def admin_catalog_schema(catalog_contract_context):
    return schemathesis.openapi.from_asgi("/api/v1/openapi.json", app)


schema = schemathesis.pytest.from_fixture("admin_catalog_schema")


@schema.include(
    method="GET",
    path=[
        "/api/v1/admin/v2/projects",
        "/api/v1/admin/v2/products",
    ],
).parametrize()
@settings(max_examples=12, deadline=None)
def test_admin_catalog_reads_match_openapi(case, catalog_contract_context):
    case.headers = case.headers or {}
    case.headers["Authorization"] = catalog_contract_context["authorization"]
    response = case.call()
    case.operation.validate_response(response, case=case)
