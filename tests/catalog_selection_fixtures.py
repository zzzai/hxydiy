from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.domain.catalog_options import _snapshot_hash
from app.main import app
from app.models import (
    PriceBook,
    Project,
    ProjectCatalogVersion,
    ProjectOptionChoice,
    ProjectOptionGroup,
    Store,
)


@dataclass
class CatalogSelectionScenario:
    client: TestClient
    customer_headers: dict[str, str]
    store_id: int
    session_id: str
    qiqing_id: int
    xiangxiang_id: int
    xiaoqi_id: int
    referenced_small_project_id: int
    local_project_id: int
    qiqing_version_id: int
    qiqing_small_group_id: int
    qiqing_cupping_choice_id: int
    qiqing_linked_choice_id: int


@pytest.fixture
def scenario() -> CatalogSelectionScenario:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_get_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        with session_local() as db:
            store = Store(store_code="catalog-selection-store", name="顾客目录测试门店", address="测试地址")
            db.add(store)
            db.flush()

            qiqing = Project(store_id=store.id, code="hxy-qiqing-30", category="bath", name="草本泡脚", publication_status="published")
            xiangxiang = Project(store_id=store.id, code="hxy-xiangxiang-60", category="bath", name="草本沐足", publication_status="published")
            xiaoqi = Project(store_id=store.id, code="hxy-xiaoqi-90", category="bath", name="招牌草本沐足", publication_status="published")
            referenced_small = Project(store_id=store.id, code="hxy-guasha-30", category="small", name="刮痧", publication_status="published")
            local_project = Project(store_id=store.id, code="hxy-jubu-30", category="local-strength", name="局部调理", publication_status="published")
            db.add_all([qiqing, xiangxiang, xiaoqi, referenced_small, local_project])
            db.flush()
            for project in (qiqing, xiangxiang, xiaoqi, referenced_small, local_project):
                db.add(PriceBook(project_id=project.id, price_type="store", amount_cents=1000))

            version = ProjectCatalogVersion(project_id=qiqing.id, version=1, status="published")
            db.add(version)
            db.flush()
            qiqing.current_published_version_id = version.id
            group = ProjectOptionGroup(catalog_version_id=version.id, code="small", name="小项", selection_mode="multiple", max_select=2)
            db.add(group)
            db.flush()
            cupping = ProjectOptionChoice(
                option_group_id=group.id,
                code="cupping",
                name="走竹罐",
                choice_type="preference",
                charge_mode="free",
                display_order=1,
            )
            linked_small = ProjectOptionChoice(
                option_group_id=group.id,
                code="guasha",
                name="刮痧",
                choice_type="linked_project",
                linked_project_id=referenced_small.id,
                charge_mode="inherit_linked_price",
                display_order=2,
            )
            db.add_all([cupping, linked_small])
            db.flush()
            version.snapshot_hash = _snapshot_hash(db, version.id)
            db.commit()

            store_id = store.id
            qiqing_id = qiqing.id
            xiangxiang_id = xiangxiang.id
            xiaoqi_id = xiaoqi.id
            referenced_small_project_id = referenced_small.id
            local_project_id = local_project.id
            qiqing_version_id = version.id
            qiqing_small_group_id = group.id
            qiqing_cupping_choice_id = cupping.id
            qiqing_linked_choice_id = linked_small.id

        session_response = client.post("/api/v1/selection-sessions", json={"store_id": store_id})
        assert session_response.status_code == 200, session_response.text
        session_body = session_response.json()
        yield CatalogSelectionScenario(
            client=client,
            customer_headers={
                "X-Selection-Token": session_body["access_token"],
                "Idempotency-Key": "catalog-selection-contract",
            },
            store_id=store_id,
            session_id=session_body["session"]["id"],
            qiqing_id=qiqing_id,
            xiangxiang_id=xiangxiang_id,
            xiaoqi_id=xiaoqi_id,
            referenced_small_project_id=referenced_small_project_id,
            local_project_id=local_project_id,
            qiqing_version_id=qiqing_version_id,
            qiqing_small_group_id=qiqing_small_group_id,
            qiqing_cupping_choice_id=qiqing_cupping_choice_id,
            qiqing_linked_choice_id=qiqing_linked_choice_id,
        )
    finally:
        client.close()
        app.dependency_overrides.clear()
        engine.dispose()
