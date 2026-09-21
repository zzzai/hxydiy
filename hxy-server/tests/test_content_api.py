import unittest
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.domain.catalog_options import _snapshot_hash
from app.main import app
from app.models import (
    OptionChoicePrice,
    PriceBook,
    Product,
    Project,
    ProjectCatalogVersion,
    ProjectOptionChoice,
    ProjectOptionGroup,
    Store,
)


class PublishedContentApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        cls.SessionLocal = sessionmaker(bind=cls.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(cls.engine)
        with cls.SessionLocal() as db:
            store = Store(store_code="content-store", name="内容测试门店", address="测试地址")
            db.add(store)
            db.flush()
            db.add_all([
                Project(store_id=store.id, code="CONTENT-PUBLISHED", category="bath", name="已发布项目", publication_status="published", display_order=2, detail_modules=[{"type": "text", "title": "服务说明", "body": "详情"}], diy_options=[{"label": "肩颈", "price_cents": 1000}]),
                Project(store_id=store.id, code="CONTENT-DRAFT", category="bath", name="草稿项目", publication_status="draft", display_order=1),
            ])
            db.add_all([
                Product(
                    store_id=store.id,
                    code="PRODUCT-LATER",
                    name="后展示商品",
                    product_type="foot",
                    price_cents=1990,
                    member_price_cents=1590,
                    display_order=20,
                    detail_modules=[{"type": "text", "body": "后展示详情"}],
                    publication_status="published",
                ),
                Product(
                    store_id=store.id,
                    code="PRODUCT-FIRST",
                    name="先展示商品",
                    product_type="heat",
                    price_cents=990,
                    display_order=10,
                    publication_status="published",
                ),
            ])
            db.flush()
            for project in db.query(Project).all():
                db.add(PriceBook(project_id=project.id, price_type="store", amount_cents=2990))
            db.commit()
            cls.store_id = store.id

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()
        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        app.dependency_overrides.clear()
        cls.engine.dispose()

    def test_public_projects_return_published_content_and_hide_drafts(self):
        response = self.client.get("/api/v1/projects", params={"store_id": self.store_id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["code"] for item in response.json()["items"]], ["CONTENT-PUBLISHED"])
        item = response.json()["items"][0]
        self.assertEqual(item["detail_modules"][0]["title"], "服务说明")
        self.assertEqual(item["diy_options"][0]["label"], "肩颈")

    def test_public_products_follow_display_order_and_return_catalog_details(self):
        response = self.client.get("/api/v1/products", params={"store_id": self.store_id})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([item["name"] for item in response.json()], ["先展示商品", "后展示商品"])
        later = response.json()[1]
        self.assertEqual(later["member_price_cents"], 1590)
        self.assertEqual(later["detail_modules"], [{
            "type": "text",
            "title": "",
            "body": "后展示详情",
            "image_url": "",
        }])
        self.assertEqual(later["display_order"], 20)

    def test_public_project_option_prices_include_only_current_effective_rows(self):
        now = datetime.now(UTC)
        with self.SessionLocal() as db:
            store = Store(store_code="content-price-store", name="价格过滤门店", address="测试地址")
            db.add(store)
            db.flush()
            project = Project(
                store_id=store.id,
                code="CONTENT-CATALOG-PRICES",
                category="bath",
                name="目录价格项目",
                publication_status="published",
            )
            db.add(project)
            db.flush()
            db.add(PriceBook(project_id=project.id, price_type="store", amount_cents=2990))
            version = ProjectCatalogVersion(project_id=project.id, version=1, status="published")
            db.add(version)
            db.flush()
            project.current_published_version_id = version.id
            group = ProjectOptionGroup(catalog_version_id=version.id, code="addons", name="加项")
            db.add(group)
            db.flush()
            choice = ProjectOptionChoice(
                option_group_id=group.id,
                code="hot-pack",
                name="热敷包",
                choice_type="dedicated_charge",
                charge_mode="custom_price",
            )
            db.add(choice)
            db.flush()
            db.add_all([
                OptionChoicePrice(
                    option_choice_id=choice.id,
                    price_type="store",
                    amount_cents=900,
                    effective_from=now - timedelta(days=10),
                    effective_to=now - timedelta(days=5),
                ),
                OptionChoicePrice(
                    option_choice_id=choice.id,
                    price_type="store",
                    amount_cents=1000,
                    effective_from=now - timedelta(days=2),
                ),
                OptionChoicePrice(
                    option_choice_id=choice.id,
                    price_type="store",
                    amount_cents=1200,
                    effective_from=now - timedelta(days=1),
                ),
                OptionChoicePrice(
                    option_choice_id=choice.id,
                    price_type="member",
                    amount_cents=800,
                    effective_from=now + timedelta(days=1),
                ),
            ])
            db.flush()
            version.snapshot_hash = _snapshot_hash(db, version.id)
            db.commit()
            project_id = project.id

        response = self.client.get(f"/api/v1/projects/{project_id}")
        self.assertEqual(response.status_code, 200, response.text)
        prices = response.json()["option_groups"][0]["choices"][0]["prices"]
        self.assertEqual(prices, [{
            "price_type": "store",
            "amount_cents": 1200,
            "effective_from": prices[0]["effective_from"],
            "effective_to": None,
        }])


if __name__ == "__main__":
    unittest.main()
