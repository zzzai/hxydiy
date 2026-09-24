from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.domain.catalog_options import _snapshot_hash
from app.main import app
from app.models import PriceBook, Project, ProjectCatalogVersion, ProjectOptionChoice, ProjectOptionGroup, Store


def test_hidden_standalone_project_remains_available_to_published_linked_catalog():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, expire_on_commit=False)
    with session_local() as db:
        store = Store(store_code="aux-visibility", name="测试门店", address="测试地址")
        db.add(store)
        db.flush()
        legacy = Project(store_id=store.id, code="legacy-cupping", category="small",
                         category_mark="辅", name="拔罐", publication_status="published")
        parent = Project(store_id=store.id, code="parent-bath", category="bath",
                         name="泡脚", publication_status="published")
        db.add_all([legacy, parent])
        db.flush()
        legacy.independently_visible = False
        db.add_all([
            PriceBook(project_id=legacy.id, price_type="store", amount_cents=5900),
            PriceBook(project_id=parent.id, price_type="store", amount_cents=9900),
        ])
        version = ProjectCatalogVersion(project_id=parent.id, version=1, status="published")
        db.add(version)
        db.flush()
        parent.current_published_version_id = version.id
        group = ProjectOptionGroup(catalog_version_id=version.id, code="extras", name="加选")
        db.add(group)
        db.flush()
        db.add(ProjectOptionChoice(option_group_id=group.id, code="cupping", name="拔罐",
                                   choice_type="linked_project", linked_project_id=legacy.id,
                                   charge_mode="inherit_linked_price"))
        db.flush()
        version.snapshot_hash = _snapshot_hash(db, version.id)
        db.commit()
        store_id, legacy_id, parent_id = store.id, legacy.id, parent.id

    def override_get_db():
        with session_local() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            listing = client.get(f"/api/v1/projects?store_id={store_id}")
            assert listing.status_code == 200, listing.text
            assert [item["id"] for item in listing.json()["items"]] == [parent_id]
            legacy_detail = client.get(f"/api/v1/projects/{legacy_id}")
            assert legacy_detail.status_code == 200, legacy_detail.text
            parent_detail = client.get(f"/api/v1/projects/{parent_id}")
            assert parent_detail.status_code == 200, parent_detail.text
            choices = parent_detail.json()["option_groups"][0]["choices"]
            assert choices[0]["linked_project_id"] == legacy_id
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
